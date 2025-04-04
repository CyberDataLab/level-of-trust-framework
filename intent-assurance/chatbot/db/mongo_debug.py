from pymongo import MongoClient
import copy

client = MongoClient("mongodb://localhost:27017/")
db = client["example_database"]
collection = db["wef_entities"]

def insert_documents():
    collection.drop()

    base_doc = {
        "vnfProvider": "Bcom",
        "serviceType": "cloud",
        "assets": [
            {
                "id": "resource-voip1",
                "type": "service",
                "serviceDesc": {
                    "serviceType": "voip",
                    "serviceSW": "asterisk",
                    "serviceVersion": "22.0.0",
                    "health": {
                        "score": 0,
                        "status": "green",
                        "symptoms": [
                            {
                                "symptomType": "Processes",
                                "objectiveIndicators": [
                                    {
                                        "indicatorType": "Stability",
                                        "indicatorValue": 0.99
                                    }
                                ]
                            }
                        ]
                    }
                },
                "subservices": [
                    {
                        "subserviceDesc": {
                            "id": "subservice-ldap1",
                            "subserviceType": "directory",
                            "subserviceSW": "open-ldap",
                            "subserviceVersion": "2.6.9",
                            "health": {
                                "score": 0,
                                "status": "green",
                                "symptoms": [
                                    {
                                        "symptomType": "Processes",
                                        "objectiveIndicators": [
                                            {
                                                "indicatorType": "Stability",
                                                "indicatorValue": 0.99
                                            }
                                        ]
                                    }
                                ]
                            }
                        }
                    }
                ]
            },
            {
                "id": "infrastructure-movistar1",
                "type": "infrastructure",
                "infrastructureDesc": {
                    "location": {
                        "country": "Spain",
                        "network": "movistar-subnet1",
                        "adressCompatibility": "IPv4",
                        "bandWidth": {
                            "bandwidthValue": 100,
                            "bandwidthUnit": "Mbps"
                        }
                    },
                    "health": {
                        "score": 0,
                        "status": "green",
                        "symptoms": [
                            {
                                "symptomType": "Networking",
                                "objectiveIndicators": [
                                    {
                                        "indicatorType": "Stability",
                                        "indicatorValue": 0.99
                                    }
                                ]
                            }
                        ]
                    }
                }
            }
        ]
    }

    # Deep copy so modifications in doc2, doc3 won't affect doc1
    doc1 = copy.deepcopy(base_doc)
    doc2 = copy.deepcopy(base_doc)
    doc3 = copy.deepcopy(base_doc)

    # doc2
    doc2["assets"][0]["serviceDesc"]["serviceVersion"] = "2.0.0"
    doc2["assets"][0]["serviceDesc"]["health"]["status"] = "red"
    doc2["assets"][0]["subservices"][0]["subserviceDesc"]["subserviceVersion"] = "2.6.8"
    doc2["assets"][0]["subservices"][0]["subserviceDesc"]["health"]["status"] = "red"
    doc2["assets"][1]["infrastructureDesc"]["location"]["country"] = "France"
    doc2["assets"][1]["infrastructureDesc"]["health"]["status"] = "red"

    # doc3
    doc3["assets"][0]["serviceDesc"]["serviceVersion"] = "3.1.5"
    doc3["assets"][0]["serviceDesc"]["health"]["status"] = "orange"
    doc3["assets"][0]["subservices"][0]["subserviceDesc"]["subserviceVersion"] = "2.6.7"
    doc3["assets"][0]["subservices"][0]["subserviceDesc"]["health"]["status"] = "orange"
    doc3["assets"][1]["infrastructureDesc"]["location"]["country"] = "Italy"
    doc3["assets"][1]["infrastructureDesc"]["health"]["status"] = "orange"

    result = collection.insert_many([doc1, doc2, doc3])
    print("Inserted documents with IDs:", result.inserted_ids)

def dynamic_query(service_version=None, service_health=None,
                  subservice_version=None, infra_country=None):
    query_filter = {}

    if service_version is not None:
        # Check for an asset with serviceDesc.serviceVersion == service_version
        query_filter["assets.serviceDesc.serviceVersion"] = service_version

    if service_health is not None:
        # Check top-level serviceDesc or subserviceDesc for this health
        query_filter["$or"] = [
            {"assets.serviceDesc.health.status": service_health},
            {"assets.subservices.subserviceDesc.health.status": service_health}
        ]

    if subservice_version is not None:
        # Check subservice version
        query_filter["assets.subservices.subserviceDesc.subserviceVersion"] = subservice_version

    if infra_country is not None:
        # Check infrastructure country
        query_filter["assets.infrastructureDesc.location.country"] = infra_country

    print("\nDynamic query filter:", query_filter)
    cursor = collection.find(query_filter)

    results = list(cursor)
    print(f"Number of matches: {len(results)}")
    for i, doc in enumerate(results, start=1):
        print(f"--- Document #{i} ---")
        print(doc)

def main():
    insert_documents()

    dynamic_query(service_version="22.0.0")
    dynamic_query(service_version="2.0.0")
    dynamic_query(service_version="3.1.5")

    dynamic_query(service_health="green")
    dynamic_query(service_health="red")
    dynamic_query(service_health="orange")

    dynamic_query(subservice_version="2.6.9")
    dynamic_query(subservice_version="2.6.8")
    dynamic_query(subservice_version="2.6.7")

    dynamic_query(infra_country="Spain")
    dynamic_query(infra_country="France")
    dynamic_query(infra_country="Italy")

if __name__ == "__main__":
    main()
