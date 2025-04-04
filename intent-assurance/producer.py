import time
import json
from uuid import uuid4
from confluent_kafka import Producer,KafkaException
import random,time
import os
from dotenv import load_dotenv
from datetime import datetime


load_dotenv()

conf = {
    'bootstrap.servers': os.getenv("BOOTSTRAP_SERVERS_URLS"),
    "enable.ssl.certificate.verification": "false",
    "api.version.request":"false",
    'security.protocol': 'SSL',
    'ssl.keystore.password': os.getenv("SECRET"),
    'ssl.key.password': os.getenv("SECRET"),
    'ssl.keystore.location': os.getenv("KEYSTORE_LOCATION"),
    'ssl.ca.location': os.getenv("CA_CERT_LOCATION"),
    'ssl.endpoint.identification.algorithm': 'https'
}

def delivery_report(errmsg, msg):
    """
    Reports the Failure or Success of a message delivery.
    Args:
        errmsg (KafkaError): The Error that occurred while message producing.
        msg (Actual message): The message that was produced.
    Note:
        In the delivery report callback the Message.key() and Message.value()
        will be the binary format as encoded by any configured Serializers and
        not the same object that was passed to produce().
        If you wish to pass the original object(s) for key and value to delivery
        report callback we recommend a bound callback or lambda where you pass
        the objects along.
    """
    if errmsg is not None:
        print("Delivery failed for Message: {} : {}".format(msg.key(), errmsg))
        return
    print('Message: {} successfully produced to Topic: {} Partition: [{}] at offset {}'.format(
        msg.key(), msg.topic(), msg.partition(), msg.offset()))


kafka_topic_name = os.getenv("TOPIC_PRODUCE_TM")

print("Starting Kafka Producer")

print("connecting to Kafka topic...")
try:
    producer1 = Producer(conf)
except KafkaException as e:
    print(f'Exception:{e}')

try:
    while True:
        #jsonString1 = f'{{"id":"9a:ea:c9:e4:50:0e", "Timestamp":{datetime.now().isoformat()}, "CPU_health": {random.randint(85,100)}, "Sensors_health": {0}, "Memory_health": {random.randint(80,100)}, "Processes_health": {random.randint(98,100)},"Disks_health": {random.randint(94,100)}, "Network_health": {random.randint(95,100)}}}'
        #jsonv1 = jsonString1.encode()
        # Asynchronously produce a message, the delivery report callback
        # will be triggered from poll() above, or flush() below, when the message has
        # been successfully delivered or failed permanently.
        #producer1.produce(topic=kafka_topic_name, key=str(uuid4()), value=jsonv1, on_delivery=delivery_report)

        # Trigger any available delivery report callbacks from previous produce() calls
        #res = producer1.poll(5)
        # Wait for any outstanding messages to be delivered and delivery report
        # callbacks to be triggered.
        #res2=producer1.flush(1)
        message = json.dumps({"ids": ["7406f4db-06dc-5d96-9e0d-793f5083f923"]})

        producer1.produce(os.getenv("TOPIC_PRODUCE_TM"), value=message)
        producer1.flush()
        print(f"[INFO] Data sent to kafka topic", os.getenv("TOPIC_PRODUCE_TM"))

        time.sleep(1)


except Exception as ex:
    print("Exception happened :", ex)

print("\n Stopping Kafka Producer")