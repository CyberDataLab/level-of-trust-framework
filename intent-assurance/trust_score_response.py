from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from additional_interfaces import router as trust_management_router  # Import router from Trust_Management_System
from typing import List, Dict, Any, Optional
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

class FilePathRequest(BaseModel):
    file_path: str
    
    class Config:
        json_schema_extra = {
            "file_path": "/path/to/your/data.json"
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

def consume_kafka_messages_old():
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

def consume_kafka_messages():
    """
    Consume messages from a Kafka Topic synchronously and compute trust scores.
    Uses the pre-computed health score from /health/node for each device ID.
    """
    consumer = Consumer(conf)
    consumer.subscribe([kafka_topic_name], on_assign=reset_offset)
    id_scores = {}  # Dictionary to track scores and counts per ID

    while True:
        # Poll for messages with 1 second timeout
        msg = consumer.poll(timeout=1.0)
        
        if msg is None:
            # No message received, assume all messages consumed
            break
        
        if msg.error():
            if msg.error().code() == KafkaError._PARTITION_EOF:
                break
            else:
                print(f"Error consuming message: {msg.error()}")
                break
        
        # Process the received message
        print(f"Received message: {msg.value().decode('utf-8')}")
        
        try:
            # Parse the message
            decoded_message = json.loads(msg.value().decode('utf-8'))
            
            # Process the single message
            device_id = decoded_message["id"]
            health_score = float(decoded_message["data"]["/health/node/trust_index"])
            
            # Update running average for this device ID
            if device_id in id_scores:
                current_avg = id_scores[device_id]["trust_index"]
                current_count = id_scores[device_id]["counter"]
                # Calculate new average
                new_avg = (current_avg * current_count + (health_score/100)) / (current_count + 1)
                id_scores[device_id]["trust_index"] = round(new_avg, 4)
                id_scores[device_id]["counter"] += 1
            else:
                # First score for this device
                id_scores[device_id] = {
                    "id": device_id,
                    "trust_index": round(health_score / 100, 4),
                    "counter": 1
                }
                
        except json.JSONDecodeError as e:
            print(f"JSON decode error: {e}")
            print(f"Raw message: {msg.value().decode('utf-8')}")
        except KeyError as e:
            print(f"Missing required field in message: {e}")
            continue

    consumer.close()
    
    # Convert dictionary to list of scores
    return list(id_scores.values())

def compute_trust_scores_from_json(file_path: str) -> List[Dict[str, Any]]:
    """
    Compute trust scores from a JSON file
    
    Args:
        file_path: Path to the JSON file containing the trust data
        
    Returns:
        List of dictionaries containing trust scores for each device ID
    """
    # Check if file exists
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    
    try:
        # Read the JSON file
        with open(file_path, 'r') as f:
            data = json.load(f)
        
        id_scores = {}  # Dictionary to track scores and counts per ID
        
        # Process each message in the JSON data
        for message in data:
            try:
                # Extract device ID and health score
                device_id = message["id"]
                health_score = float(message["data"]["/health/node/trust_index"])
                
                # Update running average for this device ID
                if device_id in id_scores:
                    current_avg = id_scores[device_id]["trust_index"]
                    current_count = id_scores[device_id]["counter"]
                    # Calculate new average
                    new_avg = (current_avg * current_count + (health_score/100)) / (current_count + 1)
                    id_scores[device_id]["trust_index"] = round(new_avg, 4)
                    id_scores[device_id]["counter"] += 1
                else:
                    # First score for this device
                    id_scores[device_id] = {
                        "id": device_id,
                        "trust_index": round(health_score / 100, 4),
                        "counter": 1
                    }
            except KeyError as e:
                print(f"Missing required field in message: {e}")
                continue
        
        # Convert dictionary to list of scores
        return list(id_scores.values())
    
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON format: {str(e)}")
    except Exception as e:
        raise Exception(f"Error processing JSON file: {str(e)}")


@app.get("/compute_trust_from_file", response_model=List[Trust_Score_Response],
        tags=["monitoring"],
        summary="Compute trust scores from a JSON file",
        description="Read a JSON file and compute average trust scores for each device ID")
async def get_trust_from_file(file_path: str = Query(..., description="Path to the JSON file containing trust data")):
    """
    Compute trust scores from a JSON file path provided as a query parameter
    
    Args:
        file_path: Path to the JSON file
        
    Returns:
        List of trust scores for each device ID
    """
    try:
        trust_scores = compute_trust_scores_from_json(file_path)
        return trust_scores
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
            
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