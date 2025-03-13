from confluent_kafka import Consumer, KafkaError
import os
import json  
import uuid  
import asyncio  
import httpx  
from dotenv import load_dotenv
from trust_score_response import consume_kafka_messages
from trust_score_response import compute_trust_scores_from_json
from confluent_kafka import Producer

load_dotenv()

conf_consumer = {
    'bootstrap.servers': os.getenv("BOOTSTRAP_SERVERS_URLS"),
    'group.id': os.getenv("CONSUMER_GROUP"),
    'security.protocol': 'SSL',
    'ssl.keystore.password': os.getenv("SECRET"),
    'ssl.key.password': os.getenv("SECRET"),
    'ssl.keystore.location': os.getenv("KEYSTORE_LOCATION"),
    'ssl.ca.location': os.getenv("CA_CERT_LOCATION"),
    'ssl.endpoint.identification.algorithm': ' ',
    'auto.offset.reset': 'earliest',  # Add this to start from earliest offset
    'enable.auto.commit': False,      # Optional: Disable auto commit to ensure we read everything
}

conf_producer = {
    'bootstrap.servers': os.getenv("BOOTSTRAP_SERVERS_URLS"),
    "enable.ssl.certificate.verification": "false",
    "api.version.request": "false",
    'security.protocol': 'SSL',
    'ssl.keystore.password': os.getenv("SECRET"),
    'ssl.key.password': os.getenv("SECRET"),
    'ssl.keystore.location': os.getenv("KEYSTORE_LOCATION"),
    'ssl.ca.location': os.getenv("CA_CERT_LOCATION"),
    'ssl.endpoint.identification.algorithm': 'https'
}

kafka_topic_name = os.getenv("TOPIC_CONSUME_TM")

print("Starting Kafka Consumer to read all messages")

# Create a Kafka Consumer instance
consumer = Consumer(conf_consumer)
producer_TID = Producer(conf_producer)

# Function to reset offset to beginning of partition
def reset_offset(consumer, partitions):
    for p in partitions:
        # Set the partition offset to beginning
        p.offset = 0
    consumer.assign(partitions)

def get_machine_uuid():
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, str(uuid.getnode())))

# Function to call the trust_management_LoTAF API
async def call_trust_management_api(uuid):
    url = "http://127.0.0.1:8000/trust_management_LoTAF"
    params = {"id": uuid}
    
    print(f"Calling trust_management_LoTAF API with UUID: {uuid}")
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params)
            
            if response.status_code == 200:
                print(f"API call successful for UUID {uuid}")
                print(f"Response: {response.json()}")
                return response.json()
            else:
                print(f"API call failed with status code: {response.status_code}")
                print(f"Error: {response.text}")
                return None
    except Exception as e:
        print(f"Error calling the API: {str(e)}")
        return None
    
def send_to_kafka_TID(data):
        message = json.dumps(data)

        producer_TID.produce(os.getenv("TOPIC_PRODUCE_LOTAF"), value=message)
        producer_TID.flush()
        print(f"[INFO] Data sent to kafka topic", os.getenv("TOPIC_PRODUCE_LOTAF"), "with value", message)
    
# Function to process message and call API if UUID matches
def process_message(msg_value):
    try:
        # Parse the message as JSON
        message_data = json.loads(msg_value)
        
        # Check if the message has the expected structure with "ids" field
        if "ids" in message_data and isinstance(message_data["ids"], list):
            # For each UUID in the message
            for uuid_value in message_data["ids"]:

                uuid_machine = "7406f4db-06dc-5d96-9e0d-793f5083f923"  # Call the function without 'self'
                if uuid_value == uuid_machine:
                    print(f"UUID matches machine UUID: {uuid_machine}")
                    # Call the API for this UUID (using asyncio to run the async function)
                    try:
                        # Path to the JSON file inside dxagent-master folder
                        json_file_path = os.path.join(os.path.dirname(__file__), 'dxagent-master', 'datos_exporter.json')
                            
                        #Call the function to compute trust scores from the JSON file
                        trust_scores = compute_trust_scores_from_json(json_file_path)
                        send_to_kafka_TID(trust_scores)
                            
                        print(f"Trust scores computed from JSON file: {trust_scores}")
                            
                    except Exception as e:
                            print(f"Error computing trust scores from JSON file: {str(e)}")
                
        else:
            print("Message doesn't contain 'ids' field or it's not a list")
            
    except json.JSONDecodeError:
        print("Failed to decode message as JSON")
    except Exception as e:
        print(f"Error processing message: {str(e)}")

# Subscribe to topics with the reset_offset callback
consumer.subscribe([kafka_topic_name], on_assign=reset_offset)

try:
    # Keep track of messages to handle end-of-data condition
    message_count = 0
    no_message_count = 0
    max_no_message_count = 10  # Number of empty polls before considering all messages read

    while True:
        msg = consumer.poll(1.0)  # Poll for messages, timeout set to 1 second

        if msg is None:
            no_message_count += 1
            # If we've received messages before and then get several empty polls,
            # assume we've read all historic messages
            if message_count > 0 and no_message_count >= max_no_message_count:
                print(f"No new messages after {max_no_message_count} polls, all history likely read.")
                # Uncomment the next line if you want to exit after reading all messages
                # break
            continue
            
        if msg.error():
            if msg.error().code() == KafkaError._PARTITION_EOF:
                # End of partition event, not an error
                print("Reached end of partition")
            else:
                print(f"Error: {msg.error()}")
        else:
            # Process the received message
            message_count += 1
            no_message_count = 0  # Reset the no-message counter
            
            # Get message value as string
            message_value = msg.value().decode('utf-8')
            print(f"Message {message_count}: {message_value}")

            # Process the message and call API if needed
            process_message(message_value)
            
            # Manually commit offsets
            consumer.commit(msg)

except KeyboardInterrupt:
    print("Consumer interrupted by user")

finally:
    # Close down consumer to commit final offsets
    consumer.close()
    print(f"Consumer closed, processed {message_count} messages")