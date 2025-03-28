from pymongo import MongoClient

client = MongoClient("mongodb://localhost:27017/")
db = client["example_database"]
collection = db["wef_entities"]

def insert_documents():
    collection.drop()

    base_doc = {
        "vnfProvider": "Bcom",
        "vnfSoftwareVersion": "1.2.1",
        "vnfmInfo": "WEF_VNFM",
        "serviceType": "cloud",
        "assets": [
            {
                "type": "resource",
                "swImageDesc": {
                    "id": "WEF_AAA_SWID",
                    "containerFormat": "BARE",
                    "diskFormat": "QCOW2",
                    "swImage": "wef_aaa_5gt",
                    "operatingSystem": "ubuntu-server-16.04-amd64"
                }
            },
            {
                "type": "resource",
                "virtualComputeDesc": [
                    {
                        "virtualComputeDescId": "VCD_WEF_AAA",
                        "virtualMemory": {
                            "virtualMemSize": 8,
                            "virtualMemSizeUnit": "GB"
                        },
                        "virtualCpu": [
                            {
                                "numVirtualCpu": 4,
                                "virtualCpuUnit": "CORE"
                            },
                            {
                                "processingFrequency": 2.5,
                                "frequencyUnit": "GHz"
                            }
                        ]
                    },
                    {
                        "health": {
                            "score": 0,
                            "status": "green",
                            "symptoms": [
                                {
                                    "symptomType": "CPU",
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
                ]
            },
            {
                "type": "resource",
                "virtualStorageDesc": [
                    {
                        "id": "VSD_WEF_AAA",
                        "swImageDesc": "WEF_AAA_SWID"
                    },
                    {
                        "typeOfStorage": "VOLUME",
                        "sizeOfStorage": 256,
                        "sizeOfStorageUnit": "GB"
                    },
                    {
                        "health": {
                            "score": 0,
                            "status": "orange",
                            "symptoms": [
                                {
                                    "symptomType": "Memory",
                                    "objectiveIndicators": [
                                        {
                                            "indicatorType": "Availability",
                                            "indicatorValue": 0.99
                                        }
                                    ]
                                }
                            ]
                        }
                    }
                ]
            },
            {
                "type": "infrastructure",
                "intCpd": {
                    "id": "wef-aaa-ens3-int",
                    "addressData": [
                        {
                            "addressType": "IP_ADDRESS",
                            "iPAddressType": "IPv4"
                        }
                    ]
                }
            }
        ]
    }

    doc1 = base_doc.copy()
    
    doc2 = base_doc.copy()
    doc2["vnfSoftwareVersion"] = "2.0.0"
    doc2["assets"][1]["virtualComputeDesc"][1]["health"]["status"] = "red"

    doc3 = base_doc.copy()
    doc3["vnfSoftwareVersion"] = "3.1.5"
    doc3["assets"][2]["virtualStorageDesc"][2]["health"]["score"] = 1

    result = collection.insert_many([doc1, doc2, doc3])
    print("Inserted documents with IDs:", result.inserted_ids)


def dynamic_query(vnf_software_version=None, health_status=None, operating_system=None):
    query_filter = {}

    if vnf_software_version is not None:
        query_filter["vnfSoftwareVersion"] = vnf_software_version

    if health_status is not None:
        query_filter["$or"] = [
            {"assets.virtualComputeDesc.health.status": health_status},
            {"assets.virtualStorageDesc.health.status": health_status}
        ]

    if operating_system is not None:
        query_filter["assets.swImageDesc.operatingSystem"] = operating_system

    print("\nDynamic query filter:", query_filter)
    cursor = collection.find(query_filter)

    results = list(cursor)
    print(f"Number of matches: {len(results)}")
    for i, doc in enumerate(results, start=1):
        print(f"--- Document #{i} ---")
        print(doc)

def main():
    insert_documents()

    # A) Filter by vnfSoftwareVersion only
    dynamic_query(vnf_software_version="2.0.0")

    # B) Filter by health_status only (e.g. 'red', 'green', 'orange')
    dynamic_query(health_status="green")

    # C) Filter by operating_system
    dynamic_query(operating_system="ubuntu-server-16.04-amd64")

    # D) Filter by both version AND health
    dynamic_query(vnf_software_version="2.0.0", health_status="red")

    # E) No filters => returns everything
    dynamic_query()

if __name__ == "__main__":
    main()
