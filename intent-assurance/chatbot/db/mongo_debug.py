import os
import json
import sys
from pymongo import MongoClient

# MongoDB connection setup
client = MongoClient('mongodb://localhost:27017/')
db_name = 'example_database'
collection_name = 'wef_entities'
db = client[db_name]
collection = db[collection_name]

# Check the execution argument
if len(sys.argv) < 2:
    print("Usage: python mongo_debug.py <query|list>")
    sys.exit(1)

execution_arg = sys.argv[1]

if execution_arg == "query":
    # Query the collection to search for the new document
    query = {
        '$or': [
            {
                '$or': [
                    {
                        '$or': [
                            {
                                '$or': [
                                    {
                                        'assets': {
                                            '$elemMatch': {
                                                'virtualStorageDesc': {
                                                    '$elemMatch': {
                                                        'sizeOfStorage': '128',
                                                        'sizeOfStorageUnit': 'GB'
                                                    }
                                                }
                                            }
                                        }
                                    },
                                    {
                                        'assets': {
                                            '$elemMatch': {
                                                'virtualComputeDesc': {
                                                    '$elemMatch': {
                                                        '$and': [
                                                            {
                                                                'virtualCpu': {
                                                                    '$elemMatch': {
                                                                        '$and': [
                                                                            {'numCore': '4'}
                                                                        ]
                                                                    }
                                                                }
                                                            }
                                                        ]
                                                    }
                                                }
                                            }
                                        }
                                    }
                                ]
                            },
                            {
                                'assets': {
                                    '$elemMatch': {
                                        '$and': [
                                            {
                                                '$or': [
                                                    {'serviceDesc.type': {'$regex': 'proxy', '$options': 'i'}},
                                                    {'subservices.subserviceDesc.type': {'$regex': 'proxy', '$options': 'i'}}
                                                ]
                                            },
                                            {
                                                '$or': [
                                                    {'serviceDesc.serviceSW': {'$regex': 'haproxy', '$options': 'i'}},
                                                    {'subservices.subserviceDesc.subserviceSW': {'$regex': 'haproxy', '$options': 'i'}}
                                                ]
                                            }
                                        ]
                                    }
                                }
                            }
                        ]
                    },
                    {
                        'assets': {
                            '$elemMatch': {
                                '$and': [
                                    {'swImageDesc.operatingSystemVersion': {'$regex': 'ubuntu', '$options': 'i'}},
                                    {'swImageDesc.operatingSystemCodename': {'$regex': 'xenial', '$options': 'i'}}
                                ]
                            }
                        }
                    }
                ]
            },
            {
                'assets': {
                    '$elemMatch': {
                        'infrastructureDesc.location.bandWidth': {
                            '$elemMatch': {
                                'bandwidthValue': 10,
                                'bandwidthUnit': {'$regex': 'gbps', '$options': 'i'}
                            }
                        }
                    }
                }
            }
        ]
    }

    # Execute the query
    cursor = collection.find(query)

    if collection.count_documents(query) > 0:
        print("Document matching the filters found in the collection.")
        for doc in cursor:
            print(doc)
    else:
        print("No document matching the filters found in the collection.")

elif execution_arg == "list":
    # List all documents in the collection
    cursor = collection.find()
    print("Listing all documents in the collection:")
    for doc in cursor:
        print(doc)

elif execution_arg == "add_instances":
    # Add all JSON documents from the instances directory
    instances_dir = os.path.join(os.path.dirname(__file__), 'instances')
    
    if not os.path.exists(instances_dir):
        print(f"Directory not found: {instances_dir}")
        sys.exit(1)

    for file_name in os.listdir(instances_dir):
        if file_name.endswith('.json'):
            file_path = os.path.join(instances_dir, file_name)
            try:
                with open(file_path, 'r') as file:
                    new_document = json.load(file)
                # Insert the document into the collection
                result = collection.insert_one(new_document)
                print(f"Document from {file_name} inserted with ID: {result.inserted_id}")
            except json.JSONDecodeError as e:
                print(f"Error decoding JSON in file {file_name}: {e}")
            except Exception as e:
                print(f"Error processing file {file_name}: {e}")

elif execution_arg == "flush":
    # Flush the collection
    try:
        collection.delete_many({})
        print("All documents in the collection have been deleted.")
    except Exception as e:
        print(f"Error flushing the collection: {e}")

else:
    print("Invalid argument. Use 'query' or 'list'.")
