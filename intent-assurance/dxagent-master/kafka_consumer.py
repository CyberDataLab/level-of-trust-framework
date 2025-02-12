import json
from confluent_kafka import Consumer, KafkaException, KafkaError

# Consumer configuration
KAFKA_BROKER  = "localhost:9092"
KAFKA_TOPIC = "dxagent_gnmi_data"
GROUP_ID = "dxagent_consumer_group"

consumer_conf = {
    'bootstrap.servers': KAFKA_BROKER,
    'group.id': GROUP_ID,
    'auto.offset.reset': 'earliest' # Read from the start if no history available
}

consumer = Consumer(consumer_conf)
consumer.subscribe([KAFKA_TOPIC])

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
        print(f"[INFO] Received data: {json.dumps(data, indent=4)}")

except KeyboardInterrupt:
    print(f"[INFO] Stopping Kafka Consumer...")

finally:
    consumer.close()