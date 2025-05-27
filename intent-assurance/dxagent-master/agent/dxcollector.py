import json
import yaml
import base64
import time
import argparse
import os
import uuid
from pathlib import Path
from uuid import uuid4
#from dotenv import load_dotenv
from google.protobuf import json_format
from cisco_gnmi import ClientBuilder
from confluent_kafka import Producer

# gNMI Server configuration
GNMI_SERVER = "0.0.0.0:50051"  # Exporter address
XPATHS = ["/health"]  # Root path to fetch all data
GNMI_MODE = "SAMPLE"  # Subscription mode: SAMPLE, ON_CHANGE, POLL
# Kafka configuration
KAFKA_BROKER = "localhost:9092"
KAFKA_TOPIC = "dxagent_gnmi_data"

# Get the base directory
# BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
# env_path = Path(BASE_DIR).joinpath('intent-assurance', '.env')

# if not env_path.exists():
#     raise FileNotFoundError(f"Environment file not found at: {env_path}")

# print(f"Loading environment from: {env_path}")
# load_dotenv(env_path)

# Update the conf dictionary to use Path.joinpath()
# conf = {
#     'bootstrap.servers': os.getenv("BOOTSTRAP_SERVERS_URLS"),
#     "enable.ssl.certificate.verification": "false",
#     "api.version.request": "false",
#     'security.protocol': 'SSL',
#     'ssl.keystore.password': os.getenv("SECRET"),
#     'ssl.key.password': os.getenv("SECRET"),
#     'ssl.keystore.location': str(Path(BASE_DIR).joinpath('intent-assurance', os.getenv("KEYSTORE_LOCATION") or '')),
#     'ssl.ca.location': str(Path(BASE_DIR).joinpath('intent-assurance', os.getenv("CA_CERT_LOCATION") or '')),
#     'ssl.endpoint.identification.algorithm': 'https'
# }

class GNMIDataCollector:
    def __init__(self, output_format, output_file, kafka_enabled):
        self.target = GNMI_SERVER
        self.output_format = output_format.lower()  # Ensure lowercase format
        self.output_file = output_file if output_file else f"datos_exporter.{self.output_format}"
        self.client = self.connect_to_gnmi()

        self.kafka_enabled = kafka_enabled

        if self.kafka_enabled:
            self.producer = Producer({'bootstrap.servers': KAFKA_BROKER})
            #self.producer_TID = Producer(conf)

    def connect_to_gnmi(self):
        """Establishes connection with the gNMI Exporter"""
        builder = ClientBuilder(self.target)
        builder.set_secure_from_target()  # Use SSL if required
        return builder.construct()

    def save_data(self, data):
        """Saves data in the chosen format (JSON or YAML)"""
        if self.output_format == "json":
            with open(self.output_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        elif self.output_format == "yaml":
            with open(self.output_file, "w", encoding="utf-8") as f:
                yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
        else:
            print("[ERROR] Unsupported format. Use 'json' or 'yaml'.")
            return
        print(f"[INFO] Data saved to {self.output_file}")

    def send_to_kafka(self, data):
        message = json.dumps(data)
        self.producer.produce(KAFKA_TOPIC, value=message)
        self.producer.flush()
        print(f"[INFO] Data sent to kafka topic '{KAFKA_TOPIC}'")


    def send_to_kafka_TID(self, data):
        message = json.dumps(data)

        self.producer_TID.produce(os.getenv("TOPIC_PRODUCE_LOTAF"), value=message)
        self.producer_TID.flush()
        print(f"[INFO] Data sent to kafka topic", os.getenv("TOPIC_PRODUCE_LOTAF"))

    def get_machine_uuid(self):
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, str(uuid.getnode())))

    def fetch_data(self):
        """Fetches real-time data and saves it in JSON or YAML format"""
        collected_data = []

        try:
            for response in self.client.subscribe_xpaths(xpath_subscriptions=XPATHS, sub_mode=GNMI_MODE):
                # Convert gNMI message to JSON
                response_json = json.loads(json_format.MessageToJson(response))

                if "update" in response_json:
                    timestamp = response_json["update"]["timestamp"]
                    updates = response_json["update"]["update"]

                    entry = {"id": self.get_machine_uuid(), "timestamp": timestamp, "data": {}}

                    for update in updates:
                        path = update["path"]["elem"]
                        path_str = "/" + "/".join([p["name"] for p in path])

                        # Extract value and handle base64 JSON
                        if "jsonVal" in update["val"]:
                            value = base64.b64decode(update["val"]["jsonVal"]).decode("utf-8")
                            try:
                                value = json.loads(value)  # Try converting to real JSON
                            except json.JSONDecodeError:
                                pass
                        elif "intVal" in update["val"]:
                            value = update["val"]["intVal"]
                        elif "stringVal" in update["val"]:
                            value = update["val"]["stringVal"]
                        elif "floatVal" in update["val"]:
                            value = update["val"]["floatVal"]
                        else:
                            value = "UNKNOWN"

                        entry["data"][path_str] = value

                    # Modify the entry with trust index before adding to collected_data
                    entry = self.calculate_trust_index(entry)
                    collected_data.append(entry)

                    # Save in the chosen format
                    self.save_data(collected_data)

                    # Send to kafka
                    if self.kafka_enabled:
                        self.send_to_kafka(entry)
                        #self.send_to_kafka_TID(entry)

                # Time control between samples
                # time.sleep(5)

        except KeyboardInterrupt:
            print("\n[INFO] Stopping data collection.")

    def calculate_trust_index(self, entry):
        """
        Calculate the trust index by averaging all numeric values in the data dictionary
        that have a path starting with '/health/node/'.
        
        Args:
            entry (dict): The data entry containing 'data' with health metrics
            
        Returns:
            dict: The modified entry with added trust_index
        """
        if not entry or 'data' not in entry:
            return entry
        
        health_values = []
        
        # Extract numeric values from paths starting with '/health/node/'
        for path, value in entry['data'].items():
            if path.startswith('/health/node/'):
                try:
                    # Convert value to float if it's a string representing a number
                    if isinstance(value, str) and value.replace('.', '', 1).isdigit():
                        health_values.append(float(value))
                    elif isinstance(value, (int, float)):
                        health_values.append(float(value))
                except (ValueError, TypeError):
                    # Skip values that can't be converted to float
                    continue
        
        # Calculate average if there are valid values
        if health_values:
            trust_index = sum(health_values) / len(health_values)
            # Round to 2 decimal places
            trust_index = round(trust_index, 2)
            # Add the trust index to the entry
            entry['data']['/health/node/trust_index'] = trust_index
        
        return entry

def start_collector(format_type, output_file, kafka_enabled):
    """Function to start data collection"""
    print("[INFO] Press CTRL+C to quit.")
    collector = GNMIDataCollector(format_type, output_file, kafka_enabled)
    collector.fetch_data()
