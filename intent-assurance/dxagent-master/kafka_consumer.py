import json
from confluent_kafka import Consumer, KafkaException, KafkaError
import morph_kgc
from neo4j import GraphDatabase
import os
import csv
import time
from collections import deque

KAFKA_BROKER = "192.168.56.1:9092"
KAFKA_TOPIC = "dxagent_gnmi_data"
GROUP_ID = "dxagent_consumer_group"

NEO4J_URI = "bolt://localhost:7687"
USERNAME = "neo4j"
PASSWORD = "password123"

WINDOW_SIZE = 6
ALPHA = 0.4

ENTITY_HISTORY = {}

consumer_conf = {
    "bootstrap.servers": KAFKA_BROKER,
    "group.id": GROUP_ID,
    "auto.offset.reset": "earliest"
}

consumer = Consumer(consumer_conf)
consumer.subscribe([KAFKA_TOPIC])

START_TIME = time.time()

def calculate_level_of_trust(entity_id, current_health):
    if entity_id not in ENTITY_HISTORY:
        ENTITY_HISTORY[entity_id] = deque(maxlen=WINDOW_SIZE)

    window = ENTITY_HISTORY[entity_id]

    if len(window) == 0:
        historical_average = current_health
    else:
        historical_average = sum(window) / len(window)

    lot = (ALPHA * current_health) + ((1 - ALPHA) * historical_average)
    window.append(current_health)

    return round(lot, 2), round(historical_average, 2)

def get_path(relative_path):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    if not os.path.isabs(relative_path):
        absolute_path = os.path.normpath(os.path.join(base_dir, relative_path))
    else:
        absolute_path = relative_path
    return absolute_path.replace("\\", "/")

def ensure_dirs():
    os.makedirs(get_path("metrics"), exist_ok=True)
    os.makedirs(get_path("generated"), exist_ok=True)

def health_status_from_score(score):
    if score >= 95:
        return "Healthy"
    elif score >= 75:
        return "Warning"
    return "Critical"

def infer_symptom_type(service_path):
    service_path = (service_path or "").lower()
    if "cpu" in service_path:
        return "CPU"
    if "mem" in service_path:
        return "Memory"
    if "proc" in service_path:
        return "Processes"
    if "net" in service_path or "/if" in service_path:
        return "Networking"
    return "VirtualMachines"

def write_mem_csv(provider_id, service, health):
    if service != "/node/bm/mem":
        return

    csv_file = get_path(os.path.join("metrics", f"{provider_id}_mem_health.csv"))
    fieldnames = ["time", "health_score"]

    now_time = time.time()
    time_value = now_time - START_TIME
    write_header = not os.path.exists(csv_file)

    with open(csv_file, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        writer.writerow({
            "time": round(time_value, 2),
            "health_score": health
        })

def write_host_timeseries_csv(provider_id, sub_id, service, instance_name, health, lot_value, historical_avg):
    csv_dir = get_path("metrics")
    os.makedirs(csv_dir, exist_ok=True)
    csv_file = os.path.join(csv_dir, f"{provider_id}_host_timeseries.csv")
    fieldnames = ["timestamp","elapsed_sec","host","asset_id","health_score","level_of_trust","historical_average"]

    now_time = time.time()
    elapsed = now_time - START_TIME
    write_header = not os.path.exists(csv_file)

    with open(csv_file, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        writer.writerow({
            "timestamp": round(now_time, 3),
            "elapsed_sec": round(elapsed, 2),
            "host": provider_id,
            "asset_id": sub_id,
            "health_score": health,
            "level_of_trust": lot_value,
            "historical_average": historical_avg
        })

    print(f"[CSV] wrote host timeseries -> {csv_file}")
    
def build_semantic_json(data, provider_id):
    entries = data.get("data", {})
    subservices_block = entries.get("/subservices", {})
    subservices = subservices_block.get("subservices", [])

    semantic_json = []

    for sub in subservices:
        sub_id = sub.get("id")
        if not sub_id:
            continue

        label = sub.get("label", sub_id)
        params = sub.get("subservice-parameters", {}) or {}
        service = params.get("service")
        instance_name = params.get("instance-name")
        health = sub.get("health-score")

        if health is None:
            continue

        entity_id = f"{provider_id}:{sub_id}"
        lot_value, historical_avg = calculate_level_of_trust(entity_id, health)

        print(f"[{provider_id}] Asset: {sub_id} | Health: {health} | Hist. Avg (H_T): {historical_avg} | Computed LoT: {lot_value}")

        health_ref = f"{provider_id}__{sub_id}".replace("/", "_").replace("[", "_").replace("]", "_")
        health_status = health_status_from_score(health)

        semantic_json.append({
            "Asset": {
                "identifier": sub_id,
                "label": label,
                "assetType": "Subservice",
                "service": service,
                "instanceName": instance_name,
                "endpoint": provider_id,
                "healthRef": health_ref
            }
        })

        semantic_json.append({
            "Health": {
                "identifier": health_ref,
                "healthScore": health,
                "connectionStatus": health_status,
                "levelOfTrust": lot_value,
                "historicalAverage": historical_avg,
                "assetRef": sub_id
            }
        })

        for dep in sub.get("dependencies", []) or []:
            target = dep.get("id")
            dep_type = dep.get("dependency-type", "impacting-dependency")
            if target:
                semantic_json.append({
                    "Dependency": {
                        "source": sub_id,
                        "target": target,
                        "dependencyType": dep_type
                    }
                })

        for symptom in sub.get("symptoms", []) or []:
            symptom_id = symptom.get("id", f"symptom_{health_ref}")
            description = symptom.get("label", "Unknown symptom")

            semantic_json.append({
                "Symptom": {
                    "identifier": symptom_id,
                    "description": description,
                    "symptomType": infer_symptom_type(service),
                    "assetRef": sub_id
                }
            })

        # write_mem_csv(provider_id, service, health)
        write_host_timeseries_csv(
            provider_id=provider_id,
            sub_id=sub_id,
            service=service,
            instance_name=instance_name,
            health=health,
            lot_value=lot_value,
            historical_avg=historical_avg
        )

    json_output_path = get_path(os.path.join("generated", f"semantic_{provider_id}.json"))
    with open(json_output_path, "w", encoding="utf-8") as demo_file:
        json.dump(semantic_json, demo_file, indent=2, ensure_ascii=False)

    return json_output_path

def write_performance_csv(provider_id, message_id, kafka_ms, mapping_ms, load_ms, total_ms, end_to_end_ms):
    csv_dir = get_path("metrics")
    os.makedirs(csv_dir, exist_ok=True)

    csv_file = os.path.join(csv_dir, f"{provider_id}_performance.csv")
    fieldnames = [
        "timestamp",
        "elapsed_sec",
        "host",
        "message_id",
        "kafka_processing_time_ms",
        "kg_mapping_time_ms",
        "kg_load_time_ms",
        "kg_total_time_ms",
        "end_to_end_time_ms"
    ]

    now_time = time.time()
    elapsed = now_time - START_TIME
    write_header = not os.path.exists(csv_file)

    with open(csv_file, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        writer.writerow({
            "timestamp": round(now_time, 3),
            "elapsed_sec": round(elapsed, 2),
            "host": provider_id,
            "message_id": message_id,
            "kafka_processing_time_ms": round(kafka_ms, 3),
            "kg_mapping_time_ms": round(mapping_ms, 3),
            "kg_load_time_ms": round(load_ms, 3),
            "kg_total_time_ms": round(total_ms, 3),
            "end_to_end_time_ms": round(end_to_end_ms, 3)
        })

def ensure_mapping_file():
    mapping_path = get_path(os.path.join("generated", "semantic-mapping.rml.ttl"))

    mapping_content = """@prefix rml: <http://semweb.mmlab.be/ns/rml#> .
@prefix rr: <http://www.w3.org/ns/r2rml#> .
@prefix ql: <http://semweb.mmlab.be/ns/ql#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix dct: <http://purl.org/dc/terms/> .
@prefix lotaf: <https://github.com/CyberDataLab/level-of-trust-framework/tree/main/Knowledge-graph-for-LoTAF/> .

<#AssetMapping>
  rml:logicalSource [
    rml:source "{json_path}" ;
    rml:referenceFormulation ql:JSONPath ;
    rml:iterator "$[*].Asset"
  ] ;
  rr:subjectMap [
    rr:template "https://example.org/asset/{identifier}" ;
    rr:class lotaf:Asset
  ] ;
  rr:predicateObjectMap [
    rr:predicate dct:identifier ;
    rr:objectMap [ rml:reference "identifier" ]
  ] ;
  rr:predicateObjectMap [
    rr:predicate rdfs:label ;
    rr:objectMap [ rml:reference "label" ]
  ] ;
  rr:predicateObjectMap [
    rr:predicate lotaf:assetType ;
    rr:objectMap [ rml:reference "assetType" ]
  ] ;
  rr:predicateObjectMap [
    rr:predicate lotaf:endpoint ;
    rr:objectMap [ rml:reference "endpoint" ]
  ] ;
  rr:predicateObjectMap [
    rr:predicate lotaf:exposes ;
    rr:objectMap [ rr:template "https://example.org/health/{healthRef}" ]
  ] .

<#HealthMapping>
  rml:logicalSource [
    rml:source "{json_path}" ;
    rml:referenceFormulation ql:JSONPath ;
    rml:iterator "$[*].Health"
  ] ;
  rr:subjectMap [
    rr:template "https://example.org/health/{identifier}" ;
    rr:class lotaf:Health
  ] ;
  rr:predicateObjectMap [
    rr:predicate dct:identifier ;
    rr:objectMap [ rml:reference "identifier" ]
  ] ;
  rr:predicateObjectMap [
    rr:predicate lotaf:healthScore ;
    rr:objectMap [ rml:reference "healthScore" ]
  ] ;
  rr:predicateObjectMap [
    rr:predicate lotaf:connectionStatus ;
    rr:objectMap [ rml:reference "connectionStatus" ]
  ] ;
  rr:predicateObjectMap [
    rr:predicate lotaf:historicalAverage ;
    rr:objectMap [ rml:reference "historicalAverage" ]
  ] ;
  rr:predicateObjectMap [
    rr:predicate lotaf:levelOfTrust ;
    rr:objectMap [ rml:reference "levelOfTrust" ]
  ] ;
  rr:predicateObjectMap [
    rr:predicate lotaf:evaluates ;
    rr:objectMap [ rr:template "https://example.org/asset/{assetRef}" ]
  ] .

<#SymptomMapping>
  rml:logicalSource [
    rml:source "{json_path}" ;
    rml:referenceFormulation ql:JSONPath ;
    rml:iterator "$[*].Symptom"
  ] ;
  rr:subjectMap [
    rr:template "https://example.org/symptom/{identifier}" ;
    rr:class lotaf:Symptom
  ] ;
  rr:predicateObjectMap [
    rr:predicate dct:identifier ;
    rr:objectMap [ rml:reference "identifier" ]
  ] ;
  rr:predicateObjectMap [
    rr:predicate dct:description ;
    rr:objectMap [ rml:reference "description" ]
  ] ;
  rr:predicateObjectMap [
    rr:predicate lotaf:symptomType ;
    rr:objectMap [ rml:reference "symptomType" ]
  ] ;
  rr:predicateObjectMap [
    rr:predicate lotaf:pertains ;
    rr:objectMap [ rr:template "https://example.org/asset/{assetRef}" ]
  ] .

<#DependencyMapping>
  rml:logicalSource [
    rml:source "{json_path}" ;
    rml:referenceFormulation ql:JSONPath ;
    rml:iterator "$[*].Dependency"
  ] ;
  rr:subjectMap [
    rr:template "https://example.org/asset/{source}"
  ] ;
  rr:predicateObjectMap [
    rr:predicate lotaf:dependsOn ;
    rr:objectMap [ rr:template "https://example.org/asset/{target}" ]
  ] .
"""
    with open(mapping_path, "w", encoding="utf-8") as f:
        f.write(mapping_content)

    return mapping_path

def mapping_data(json_file, provider_id):
    mapping_template_path = ensure_mapping_file()

    with open(mapping_template_path, "r", encoding="utf-8") as f:
        mapping_content = f.read().replace("{json_path}", json_file.replace("\\", "/"))

    concrete_mapping_path = get_path(os.path.join("generated", f"semantic-mapping-{provider_id}.rml.ttl"))
    with open(concrete_mapping_path, "w", encoding="utf-8") as f:
        f.write(mapping_content)

    mapping_config = f"""
[CONFIGURATION]
output_file={get_path(os.path.join("generated", f"demo_{provider_id}.nt"))}
output_format=N-TRIPLES

[DataSource1]
mappings={concrete_mapping_path}
"""

    g = morph_kgc.materialize(mapping_config)

    absolute_rdf_path = get_path(os.path.join("generated", f"demo_{provider_id}.rdf"))
    g.serialize(destination=absolute_rdf_path, format="xml")

    print(f"[MORPH_KGC] Mapped telemetry data for {provider_id}")
    return absolute_rdf_path

driver = GraphDatabase.driver(NEO4J_URI, auth=(USERNAME, PASSWORD))

def ensure_neo4j_n10s():
    try:
        with driver.session() as session:
            session.run("CREATE CONSTRAINT n10s_unique_uri IF NOT EXISTS FOR (r:Resource) REQUIRE r.uri IS UNIQUE")
            session.run("CALL n10s.graphconfig.init()")
    except Exception:
        try:
            with driver.session() as session:
                session.run("CALL n10s.graphconfig.show()")
        except Exception as e:
            print(f"[NEO4J WARNING] n10s may not be initialized correctly: {e}")

def clear_host_subgraph_neo4j(host_id):
    try:
        with driver.session() as session:
            query = """
            MATCH (a:ns0__Asset)
            WHERE a.ns0__endpoint = $host
            OPTIONAL MATCH (h:ns0__Health)-[:ns0__evaluates]->(a)
            OPTIONAL MATCH (s)-[:ns0__pertains]->(a)
            WITH collect(DISTINCT a) + collect(DISTINCT h) + collect(DISTINCT s) AS nodes
            UNWIND nodes AS n
            WITH DISTINCT n
            DETACH DELETE n
            """
            session.run(query, host=host_id)
            print(f"[NEO4J] Cleared subgraph for host {host_id}")
    except Exception as e:
        print(f"[NEO4J ERROR] Failed to clear host subgraph for {host_id}: {e}")

def load_triplets_neo4j(rdf_file_path):
    try:
        with open(rdf_file_path, "r", encoding="utf-8") as f:
            rdf_content = f.read()

        with driver.session() as session:
            query = """
            CALL n10s.rdf.import.inline($rdf_string, 'RDF/XML')
            """
            session.execute_write(lambda tx: tx.run(query, rdf_string=rdf_content))
            print("[NEO4J] Triplets loaded successfully into the Knowledge Graph")
    except Exception as e:
        print(f"[NEO4J ERROR] Failed to load inline RDF into the graph: {e}")

print(f"[INFO] Listening to Kafka topic '{KAFKA_TOPIC}'")

ensure_dirs()
ensure_neo4j_n10s()

try:
    while True:
        msg = consumer.poll(timeout=1.0)

        if msg is None:
            continue

        if msg.error():
            if msg.error().code() == KafkaError._PARTITION_EOF:
                continue
            raise KafkaException(msg.error())

        data = json.loads(msg.value().decode("utf-8"))
        provider_id = data.get("id", "unknown_provider")
        message_id = data.get("timestamp", str(int(time.time() * 1000)))

        t_total_start = time.perf_counter()

        t_kafka_start = time.perf_counter()
        json_file = build_semantic_json(data, provider_id)
        t_kafka_end = time.perf_counter()

        t_mapping_start = time.perf_counter()
        mapped_data = mapping_data(json_file, provider_id)
        t_mapping_end = time.perf_counter()

        t_load_start = time.perf_counter()
        clear_host_subgraph_neo4j(provider_id)
        load_triplets_neo4j(mapped_data)
        t_load_end = time.perf_counter()

        kafka_ms = (t_kafka_end - t_kafka_start) * 1000
        mapping_ms = (t_mapping_end - t_mapping_start) * 1000
        load_ms = (t_load_end - t_load_start) * 1000
        total_ms = (t_mapping_end - t_mapping_start + t_load_end - t_load_start) * 1000
        end_to_end_ms = (t_load_end - t_total_start) * 1000

        write_performance_csv(provider_id, message_id, kafka_ms, mapping_ms, load_ms, total_ms, end_to_end_ms)

except KeyboardInterrupt:
    print("[INFO] Stopping Kafka Consumer...")

finally:
    consumer.close()
    driver.close()