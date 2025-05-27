import json
from confluent_kafka import Consumer, KafkaException, KafkaError
import morph_kgc
import tempfile
from neo4j import GraphDatabase
import os
import csv
import time


# Consumer configuration
KAFKA_BROKER  = "localhost:9092"
KAFKA_TOPIC = "dxagent_gnmi_data"
GROUP_ID = "dxagent_consumer_group"

NEO4J_URI = "bolt://localhost"
USERNAME = "neo4j"
PASSWORD = "PASSWORD"

consumer_conf = {
    'bootstrap.servers': KAFKA_BROKER,
    'group.id': GROUP_ID,
    'auto.offset.reset': 'earliest' # Read from the start if no history available
}

consumer = Consumer(consumer_conf)
consumer.subscribe([KAFKA_TOPIC])

START_TIME = time.time()


def get_path(relative_path):

    base_dir = os.path.dirname(os.path.abspath(__file__)) # Absolute route of actual script

    if not os.path.isabs(relative_path):
        absolute_path = os.path.normpath(os.path.join(base_dir, relative_path))
    else:
        absolute_path = relative_path

    absolute_path = absolute_path.replace("\\", "/")

    return absolute_path

def parse_json(data):

    entries = data["data"]
    ontology_json = []
    

    for key, subservice in entries.items():

        symptoms = subservice.get("symptoms", [])
        if symptoms:
            symptom = symptoms[0]["label"]
            #print(f"[INFO] symptom = {symptom}")
            symptom_obj = {
                "Symptom": {
                    "description": symptom
                }
            }
            ontology_json.append(symptom_obj)

        health = subservice.get("health-score")
        if health is not None:
            if health >= 80:
                health_status = "GreenHealthStatus"
            elif health >= 50 and health < 80:
                health_status = "OragneHealthStatus"
            else:
                health_status = "RedHealthStatus"
            health_obj = {
                "Health": {
                    "healthScore": health,
                    "healthStatus": health_status
                }
            }
            if symptoms:
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
                # Guardar en CSV
                csv_file = "bm_mem_health.csv"
                fieldnames = ["time", "health_score"]
                # Obtener los valores
                now_time = time.time()
                time_value = now_time - START_TIME
                health_score = subservice.get("health-score")
                # Escribir en el CSV (añadiendo si ya existe)
                write_header = not os.path.exists(csv_file)
                with open(csv_file, "a", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    if write_header:
                        writer.writeheader()
                    writer.writerow({"time": time_value, "health_score": health_score})
                
            
    file_str = json.dumps(ontology_json, indent=2)
    with open("demo.json", "w") as demo_file:
        demo_file.write(file_str)

    return get_path("demo.json")

def mapping_data(file):

    mapping_path =  f"""
                    [DataSource]
                    mappings: /home/alfonso/Escritorio/tfg/level-of-trust-framework/Knowledge-graph-for-LoTAF/Ontology_implementation/nuevo-mapping.rml.ttl
                    file_path: {file}
                """

    # Generar las tripletas RDF
    g = morph_kgc.materialize(mapping_path)

    # Guardar las tripletas en un archivo RDF
    absolute_path = get_path("demo.rdf")
    g.serialize(destination=absolute_path, format="xml")


    print(f"[MORPH_KGC] Mapped data")
    return absolute_path

    



# Connection with Neo4j
driver = GraphDatabase.driver(NEO4J_URI, auth=(USERNAME, PASSWORD))

def load_triplets_ne4j(triplets):
    with driver.session() as session:
        # Import RDF data with neosemantics
        query = f"""
                CALL n10s.rdf.import.fetch("file:///{triplets}", 'RDF/XML')
                """
        # Execute command
        session.execute_write(lambda tx: tx.run(query))
        print(f"[NEO4J] Triplets loaded")


print(f"[INFO] Listening to Kafka topic '{KAFKA_TOPIC}'")

try:
    while True:
        msg = consumer.poll(timeout=1.0)

        if msg is None:
            continue # No new messages, waiting...

        if msg.error():
            if msg.error().code() == KafkaError._PARTITION_EOF:
                continue    # End of partition, waiting more data...
            else:
                raise KafkaException(msg.error())
            

        data = json.loads(msg.value().decode('utf-8'))
        #print(f"[INFO] Received data: {json.dumps(data, indent=4)}")
        json_file = parse_json(data)
        mapped_data = mapping_data(json_file)
        load_triplets_ne4j(mapped_data)

except KeyboardInterrupt:
    print(f"[INFO] Stopping Kafka Consumer...")

finally:
    consumer.close()