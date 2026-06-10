import json
from confluent_kafka import Consumer, KafkaException, KafkaError
import morph_kgc
from neo4j import GraphDatabase
import os
import csv
import time
from colections import deque


KAFKA_BROKER = "localhost:9092"
KAFKA_TOPIC = "dxagent_gnmi_data"
GROUP_ID = "dxagent_consumer_group"

NEO4J_URI = "bolt://localhost:7687"
USERNAME = "neo4j"
PASSWORD = "password123" # 

WINDOW_SIZE = 6  # Por ejemplo, las últimas 6 muestras (si llega cada 10s, son los últimos 60s)
ALPHA = 0.4       # Peso del estado actual (40%). El histórico tendrá un peso del 60%
# Diccionario para almacenar deques: { 'provider_A': deque([...], maxlen=12), ... }
PROVIDERS_HISTORY = {}


consumer_conf = {
    'bootstrap.servers': KAFKA_BROKER,
    'group.id': GROUP_ID,
    'auto.offset.reset': 'earliest'
}

consumer = Consumer(consumer_conf)
consumer.subscribe([KAFKA_TOPIC])

START_TIME = time.time()

def calculate_level_of_trust(provider_id, current_health):
    """
    Calcula el LoT correlacionando el Health Score actual con el rendimiento
    pasado guardado en una ventana deslizante de observación.
    """
    # Si es la primera vez que vemos al proveedor, inicializamos su ventana
    if provider_id not in PROVIDERS_HISTORY:
        PROVIDERS_HISTORY[provider_id] = deque(maxlen=WINDOW_SIZE)
    
    window = PROVIDERS_HISTORY[provider_id]
    
    # Si la ventana está vacía, la media histórica es igual al health actual
    if len(window) == 0:
        historical_average = current_health
    else:
        historical_average = sum(window) / len(window)
    
    # Aplicamos la fórmula de correlación ponderada
    lot = (ALPHA * current_health) + ((1 - ALPHA) * historical_average)
    
    # Añadimos el health actual a la ventana para la próxima muestra
    window.append(current_health)
    
    return round(lot, 2), round(historical_average, 2)

def get_path(relative_path):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    if not os.path.isabs(relative_path):
        absolute_path = os.path.normpath(os.path.join(base_dir, relative_path))
    else:
        absolute_path = relative_path
    return absolute_path.replace("\\", "/")


def parse_json(data, provider_id):
    entries = data["data"]
    ontology_json = []

    for key, subservice in entries.items():

        if not isinstance(subservice, dict):
            continue

        symptoms = subservice.get("symptoms", [])
        symptom = None
        if symptoms:
            symptom = symptoms[0]["label"]
            symptom_obj = {
                "Symptom": {
                    "description": symptom
                }
            }
            ontology_json.append(symptom_obj)

        health = subservice.get("health-score")
        if health is not None:
            lot_value, historical_avg = calculate_level_of_trust(provider_id, health)
            print(f"[{provider_id}] Health: {health} | Hist. Avg ($H_T$): {historical_avg} | Computed LoT: {lot_value}")
            
            if health >= 80:
                health_status = "GreenHealthStatus"
            elif health >= 50 and health < 80:
                health_status = "OrangeHealthStatus"
            else:
                health_status = "RedHealthStatus"
            
            # Modificamos el objeto semántico de confianza para que incluya el LoT
            health_obj = {
                "Health": {
                    "healthScore": health,
                    "healthStatus": health_status,
                    "levelOfTrust": lot_value,      # <-- INYECCIÓN EN EL GRAFO
                    "historicalAverage": historical_avg # <-- Corresponde al H_T solicitado
                }
            }
            if symptom:
                health_obj["Health"]["evaluates"] = symptom

            ontology_json.append(health_obj)
            
            
        service = subservice.get("subservice-parameters", {}).get("service")
        if service:
            asset_obj = {
                "Asset": {
                    "identifier": service,
                    "exposes": health
                }
            }
            ontology_json.append(asset_obj)

            if service == "/node/bm/mem":
                csv_dir = get_path("metrics")
                os.makedirs(csv_dir, exist_ok=True)
                csv_file = os.path.join(csv_dir, f"{provider_id}_mem_health.csv")
                
                fieldnames = ["time", "health_score"]
                now_time = time.time()
                time_value = now_time - START_TIME
                
                write_header = not os.path.exists(csv_file)
                with open(csv_file, "a", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    if write_header:
                        writer.writeheader()
                    writer.writerow({"time": time_value, "health_score": health})
                
    json_output_path = get_path(f"demo_{provider_id}.json")
    with open(json_output_path, "w") as demo_file:
        json.dump(ontology_json, demo_file, indent=2)

    return json_output_path


def mapping_data(json_file, provider_id):
    # NOTA: Asegúrate de que la ruta de 'nuevo-mapping.rml.ttl' sea correcta en tu entorno actual
    mapping_config = f"""
        [DataSource]
        mappings: {get_path("nuevo-mapping.rml.ttl")}
        file_path: {json_file}
    """

    g = morph_kgc.materialize(mapping_config)

    absolute_rdf_path = get_path(f"demo_{provider_id}.rdf")
    g.serialize(destination=absolute_rdf_path, format="xml")

    print(f"[MORPH_KGC] Mapped telemetry data for {provider_id}")
    return absolute_rdf_path


# Conexión con Neo4j
driver = GraphDatabase.driver(NEO4J_URI, auth=(USERNAME, PASSWORD))

def load_triplets_neo4j(rdf_file_path):
    """
    Lee el archivo RDF localmente desde el host y lo inyecta en el contenedor 
    de Neo4j como un String inline, evitando errores de volumen o rutas compartidas.
    """
    try:
        with open(rdf_file_path, "r", encoding="utf-8") as f:
            rdf_content = f.read()
            
        with driver.session() as session:
            query = """
            CALL n10s.rdf.import.inline($rdf_string, 'RDF/XML')
            """
            session.execute_write(lambda tx: tx.run(query, rdf_string=rdf_content))
            print(f"[NEO4J] Triplets loaded successfully into the Knowledge Graph")
    except Exception as e:
        print(f"[NEO4J ERROR] Failed to load inline RDF into the graph: {e}")


print(f"[INFO] Listening to Kafka topic '{KAFKA_TOPIC}'")

try:
    while True:
        msg = consumer.poll(timeout=1.0)

        if msg is None:
            continue

        if msg.error():
            if msg.error().code() == KafkaError._PARTITION_EOF:
                continue
            else:
                raise KafkaException(msg.error())
            
        # Procesar mensaje de Kafka
        data = json.loads(msg.value().decode('utf-8'))
        
        # Extraer el ID único del proveedor ("provider_A", "provider_B", o "provider_C")
        provider_id = data.get("id", "unknown_provider")
        
        json_file = parse_json(data, provider_id)
        mapped_data = mapping_data(json_file, provider_id)
        load_triplets_neo4j(mapped_data)

except KeyboardInterrupt:
    print(f"[INFO] Stopping Kafka Consumer...")

finally:
    consumer.close()
    driver.close()