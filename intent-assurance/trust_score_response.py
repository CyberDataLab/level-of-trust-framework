from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from additional_interfaces import router as trust_management_router  # Import router from Trust_Management_System
from typing import List
from confluent_kafka import Consumer, KafkaError
from dotenv import load_dotenv
import os
import json
import re
import uvicorn
import pyarrow.csv as pv
import pyarrow.compute as pc
import pyarrow as pa


# Initialize the FastAPI app
app = FastAPI(
    title="Level of Trust Assessment Function API",
    description="This API describes services offered by LoTAF",
    version="1.0.0",
    contact={
        "name": "Jose Maria Jorquera Valero",
        "url": "https://cyberdatalab.um.es/josemaria-jorquera/",
        "email": "josemaria.jorquera@um.es",
    },
)

load_dotenv()

conf = {
    'bootstrap.servers': os.getenv("BOOTSTRAP_SERVERS_URLS"),
    'auto.offset.reset': 'earliest',
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

# Define the Pydantic model for the response of /trust_management_LoTAF
class Trust_Score_Response(BaseModel):
    # Assuming it returns a list of dictionaries
    id: str
    trust_index: float
    
    class Config:
        json_schema_extra = {
                "id": "uuid1",
                "trust_index": 0.4,
                "counter": 1
        }


def reset_offset(consumer, partitions):
    """
    Callback that is executed when allocating partitions to the consumer.
    The offset of each partition is forced to 0 to always read from the beginning.
    """
    for partition in partitions:
        partition.offset = 0
    consumer.assign(partitions)

def fix_timestamp_field(message):
        # Use regex to find the Timestamp field and add quotes around it
        return re.sub(r'("Timestamp":\s*)(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+)', r'\1"\2"', message)

def consume_kafka_messages():
    """
    Consume messages from a Kafka Topic synchronously.
    The consumer_timeout_ms parameter ensures that if no messages are received for the specified time,
    the iteration is interrupted and all available messages are considered to have been consumed.
    """
    consumer = Consumer(conf)
    consumer.subscribe([kafka_topic_name],on_assign=reset_offset)
    messages = []
    means = {}
    overall_mean = []

    while True:
        # A message is expected for up to 1 second
        msg = consumer.poll(timeout=1.0)
        
        if msg is None:
            # No message received in this cycle, it is assumed that all available messages have been consumed.
            break
        
        if msg.error():
            # If the end of the partition is reached, the cycle can be exited.
            if msg.error().code() == KafkaError._PARTITION_EOF:
                break
            else:
                print(f"Error al consumir mensaje: {msg.error()}")
                break
        
        
        # Process the received message
        print(f"Received message: {msg.value().decode('utf-8')}")
        means = {}
        fixed_message = fix_timestamp_field(msg.value().decode('utf-8'))
                    
        try:
            decoded_message = json.loads(fixed_message)
            messages.append(decoded_message)
        except json.JSONDecodeError as e:
            print(f"JSON decode error: {e}")
            print(f"Raw message: {msg.value().decode('utf-8')}")

        for column in messages[0].keys():
            if isinstance(messages[0][column], int):
                mean_value = sum(msg[column] for msg in messages) / len(messages)
                means[column] = mean_value

        # Compute the final trust score for a kafka message
        mean_trust_score = 0
        active_dimension_number = 0

        for column, mean in means.items():
            if mean != 0.0:
                mean_trust_score += mean
                active_dimension_number += 1

        mean_trust_score = (mean_trust_score / active_dimension_number) / 100

        # Update the trust score for the corresponding ID
        for item in overall_mean:
            if item.get("id") == decoded_message["id"]:
                item["trust_index"] = round((float(item.get("trust_index")) * int(item["counter"]) + mean_trust_score)/(int(item["counter"])+1),4)
                item["counter"] += 1
            else:
                overall_mean.append({"id": decoded_message["id"], "trust_index": round(mean_trust_score,4), "counter": 1})

        if len(overall_mean) == 0:
            overall_mean.append({"id": decoded_message["id"], "trust_index": round(mean_trust_score,4), "counter": 1})

    consumer.close()
    return overall_mean

            
# Define the FastAPI route to expose the retrieve_trust_scores method
@app.get("/trust_management_LoTAF", response_model=List[Trust_Score_Response], tags=["monitoring"], summary="Get trust scores", description="Retrieve trust scores from the available computation nodes")
async def get_trust_scores():
    # Obtain the trust scores and return the result
    try:

        trust_index = consume_kafka_messages()
        return trust_index
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Include the router from Trust_Management_System.py
app.include_router(trust_management_router)


# Entry point for running the app
if __name__ == "__main__":
    # This will allow the FastAPI app to be launched as a standalone application
    uvicorn.run("trust_score_response:app", host="127.0.0.1", port=8000, reload=True)