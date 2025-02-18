from confluent_kafka import Consumer, KafkaError
import os
from dotenv import load_dotenv


load_dotenv()

conf = {
    'bootstrap.servers': os.getenv("BOOTSTRAP_SERVERS_URLS"),
    "enable.ssl.certificate.verification": "false",
    'group.id': os.getenv("CONSUMER_GROUP"),
    'security.protocol': 'SSL',
    'ssl.keystore.password': os.getenv("SECRET"),
    'ssl.key.password': os.getenv("SECRET"),
    'ssl.keystore.location': os.getenv("KEYSTORE_LOCATION"),
    'ssl.ca.location': os.getenv("CA_CERT_LOCATION") ,
    'ssl.endpoint.identification.algorithm': 'https',

}

kafka_topic_name = os.getenv("TOPIC_CONSUME")



print("Starting Kafka Consumer")

# Create a Kafka Consumer instance
consumer = Consumer(conf)

# Subscribe to topics
consumer.subscribe([kafka_topic_name])

try:
    while True:
        msg = consumer.poll(1)  # Poll for messages, timeout set to 1 second

        if msg is None:
            continue
        if msg.error():
            if msg.error().code() == KafkaError._PARTITION_EOF:
                # End of partition event, not an error
                print("Reached end of partition")
            else:
                print(f"Error: {msg.error()}")
        else:
            # Process the received message
            print(f"Received message: {msg.value().decode('utf-8')}")

except KeyboardInterrupt:
    pass

finally:
    # Close down consumer to commit final offsets.
    consumer.close()