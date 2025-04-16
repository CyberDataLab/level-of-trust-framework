from pymongo import MongoClient
import re
import json

# Entity classes
BUILD_CLASSES = ["middlebox"]
ASSET_CLASSES = ["storage_resource", "compute_resource", "operating_system", "service"]
TLA_CLASSES = ["qos_value"]

# Resource lists
CODENAME_MAP = {
    "xenial": "ubuntu",
    "noble": "ubuntu",
    "bionic": "ubuntu",
    "focal": "ubuntu",
    "jammy": "ubuntu",
}
UNIT_MAPPING = {
    "Bps": "bps",
    "KBps": "Kbps",
    "MBps": "Mbps",
    "GBps": "Gbps",
    "TBps": "Tbps"
}
AVAILABLE_DISTROS = ["ubuntu", "centos", "fedora", "windows"]
AVAILABLE_SERVICES = ["firewall", "load balancer", "ids", "ips", "proxy", "nat", "vpn", "voip", "dns", "directory"]
AVAILABLE_SERVICES_SOFTWARE = ["snort", "suricata", "pfsense", "openvswitch", "haproxy", "apache", "bind", "openldap", "asterisk"]

# MongoDB connection
client = MongoClient("mongodb://localhost:27017/")
db = client["example_database"]
collection = db["wef_entities"]

# Function to convert from Bps to bps
def to_bitspersecond(value: str, unit: str) -> dict:
    

    if unit not in UNIT_MAPPING:
        raise ValueError(f"Unsupported unit: {unit}")

    try:
        value_in_bps = float(value) * 8
        return {
            "value": value_in_bps,
            "unit": UNIT_MAPPING[unit]
        }
    except ValueError:
        raise ValueError(f"Invalid value: {value}")

# Function to parse storage resources
def parse_storage_resource(storage_str: str) -> dict:
    pattern = re.compile(r'(\d+(?:\.\d+)?)\s*([KMGTP]B)', re.IGNORECASE)

    match = pattern.search(storage_str)
    if match:
        size = match.group(1)
        unit = match.group(2).upper()
        return {"size": size, "unit": unit}
    else:
        return {"size": None, "unit": None}
    
# Function to build the MongoDB query filter for storage resources
def build_storage_filter(storage_info: dict) -> dict:
    size = storage_info.get("size")
    unit = storage_info.get("unit")
    if not size or not unit:
        return None

    return {
        "assets": {
            "$elemMatch": {
                "virtualStorageDesc": {
                    "$elemMatch": {
                        "sizeOfStorage": size,
                        "sizeOfStorageUnit": unit
                    }
                }
            }
        }
    }

# Function to parse compute resources
def parse_compute_resource(compute_str: str) -> dict:

    result = {
        "ram_size": None,
        "ram_unit": None,
        "num_cores": None,
        "freq_value": None,
        "freq_unit": None
    }

    lower_str = compute_str.lower()

    ram_pattern = re.compile(r'(\d+(?:\.\d+)?)\s*([KkMmGgTt][Bb])', re.IGNORECASE)
    ram_match = ram_pattern.search(lower_str)
    if ram_match:
        result["ram_size"] = ram_match.group(1)
        result["ram_unit"] = ram_match.group(2)

    else:
        if "core" in lower_str:
            digits = ''.join(filter(str.isdigit, lower_str))
            if digits:
                result["num_cores"] = digits
        else:
            freq_pattern = re.compile(r'(\d+(?:\.\d+)?)\s*([GM]Hz)', re.IGNORECASE)
            freq_match = freq_pattern.search(lower_str)
            if freq_match:
                result["freq_value"] = freq_match.group(1)
                result["freq_unit"] = freq_match.group(2)

    return result

# Function to build the MongoDB query filter for compute resources
def build_compute_filter(compute_info: dict) -> dict:
    conditions = []

    if compute_info["ram_size"] and compute_info["ram_unit"]:
        conditions.append({
            "virtualMemory.virtualMemSize": compute_info["ram_size"],
        })
        conditions.append({
            "virtualMemory.virtualMemSizeUnit": compute_info["ram_unit"]
        })

    # If we have CPU info
    cpu_subconditions = []
    if compute_info["num_cores"]:
        cpu_subconditions.append({"numCore": compute_info["num_cores"]})
    if compute_info["freq_value"] and compute_info["freq_unit"]:
        cpu_subconditions.append({
            "processingFrequency": compute_info["freq_value"]
        })
        cpu_subconditions.append({
            "frequencyUnit": compute_info["freq_unit"]
        })

    if cpu_subconditions:
        conditions.append({
            "virtualCpu": {
                "$elemMatch": {
                    "$and": cpu_subconditions
                }
            }
        })

    if not conditions:
        # No compute info => no filter
        return None

    return {
        "assets": {
            "$elemMatch": {
                "virtualComputeDesc": {
                    "$elemMatch": {
                        "$and": conditions
                    }
                }
            }
        }
    }

# Function to parse service resources
def extract_service(service_string: str):
    service_lower = service_string.lower()
    result = {
        "type": None,
        "software": None,
        "version": None
    }

    # Identify a known type
    for t in AVAILABLE_SERVICES:
        if t in service_lower:
            result["type"] = t
            break

    # Identify known software
    for sw in AVAILABLE_SERVICES_SOFTWARE:
        if sw in service_lower:
            result["software"] = sw
            break

    # Identify version
    if result["software"]:
        match = re.search(r'(\d+(?:\.\d+)?)', service_lower)
        if match:
            result["version"] = match.group(1)

    return result
    

# Function to build the MongoDB query for a service resource
def build_service_filter(service_info: dict) -> dict:
    conditions = []

    # If we have a type, it must appear in serviceDesc.type OR subservices.subserviceDesc.type
    if service_info.get("type"):
        service_type = service_info["type"]
        condition_type = {
            "$or": [
                {"serviceDesc.type": {"$regex": service_type, "$options": "i"}},
                {"subservices.subserviceDesc.type": {"$regex": service_type, "$options": "i"}}
            ]
        }
        conditions.append(condition_type)

    # If we have software, match serviceSW or subserviceSW
    if service_info.get("software"):
        software_value = service_info["software"]
        condition_sw = {
            "$or": [
                {"serviceDesc.serviceSW": {"$regex": software_value, "$options": "i"}},
                {"subservices.subserviceDesc.subserviceSW": {"$regex": software_value, "$options": "i"}}
            ]
        }
        conditions.append(condition_sw)

    # If we have a version, match serviceVersion or subserviceVersion
    if service_info.get("version"):
        version_value = service_info["version"]
        condition_ver = {
            "$or": [
                {"serviceDesc.serviceVersion": {"$regex": version_value, "$options": "i"}},
                {"subservices.subserviceDesc.subserviceVersion": {"$regex": version_value, "$options": "i"}}
            ]
        }
        conditions.append(condition_ver)

    # If there are no conditions, return empty => no filter
    if not conditions:
        return None

    # Combine them with $and, so each field must match in the same asset
    return {
        "assets": {
            "$elemMatch": {
                "$and": conditions
            }
        }
    }

# Function to parse os resources
def extract_distro_and_version(os_string: str):
    os_lower = os_string.lower()
    result = {
        "distro": None,
        "codename": None,
        "flavor": None,
        "version": None
    }

    for codename, mapped_distro in CODENAME_MAP.items():
        if codename in os_lower:
            result["codename"] = codename
            result["distro"] = mapped_distro
            break 

    if "server" in os_lower:
        result["flavor"] = "server"

    user_ver_match = re.search(r'(\d+(?:\.\d+)?)', os_lower)
    if user_ver_match:
        result["version"] = user_ver_match.group(1)

    return result

# Function to build the MongoDB query for an OS resource
def build_os_filter(os_info: dict) -> dict:
    conditions = []

    # distro => operatingSystemVersion
    if os_info["distro"]:
        conditions.append({
            "swImageDesc.operatingSystemVersion": {
                "$regex": os_info["distro"],
                "$options": "i"
            }
        })

    # codename => operatingSystemCodename
    if os_info["codename"]:
        conditions.append({
            "swImageDesc.operatingSystemCodename": {
                "$regex": os_info["codename"],
                "$options": "i"
            }
        })

    # flavor => operatingSystemVersion
    if os_info["flavor"]:
        conditions.append({
            "swImageDesc.operatingSystemVersion": {
                "$regex": os_info["flavor"],
                "$options": "i"
            }
        })

    # version => operatingSystemVersion
    if os_info["version"]:
        conditions.append({
            "swImageDesc.operatingSystemVersion": {
                "$regex": os_info["version"],
                "$options": "i"
            }
        })

    if not conditions:
        # No OS info => no filter
        return None

    return {
        "assets": {
            "$elemMatch": {
                "$and": conditions
            }
        }
    }

# Function to parse qos values
def parse_qos_value(qos_str: str) -> dict:
    qos_value_lower = qos_str.lower()
    result = {
        "value": None,
        "unit": None
    }

    qos_unit_pattern = re.compile(r'(\d+(?:\.\d+)?)\s*([KkMmGgTt]bps)', re.IGNORECASE)
    qos_unit_match = qos_unit_pattern.search(qos_value_lower)
    if qos_unit_match:
        result["value"] = qos_unit_match.group(1)
        result["unit"] = qos_unit_match.group(2)
    
    return result

# Function to build the MongoDB filter for qos values
def build_qos_filter(qos_info: dict) -> dict:
    value = qos_info.get("value")
    unit = qos_info.get("unit")
    if not value or not unit:
        return None

    return {
        "assets": {
            "$elemMatch": {
                "infrastructureDesc.location.bandWidth": {
                    "$elemMatch": {
                        "bandwidthValue": int(value),
                        "bandwidthUnit": {"$regex": unit, "$options": "i"}
                    }
                }
            }
        }
    }

# Function to merge two MongoDB query filters
def merge_filters(filter1: dict, filter2: dict) -> dict:
    if not filter1:
        return filter2
    if not filter2:
        return filter1

    if "$and" in filter1 and "$and" in filter2:
        return {
            "$and": filter1["$and"] + filter2["$and"]
        }
    elif "$and" in filter1:
        return {
            "$and": filter1["$and"] + [filter2]
        }
    elif "$and" in filter2:
        return {
            "$and": [filter1] + filter2["$and"]
        }
    else:
        return {
            "$and": [filter1, filter2]
        }

# Function to perform a dynamic query on the MongoDB
def dynamic_query(storage_resources, compute_resources,
                  os_resources, service_resources, qos_values) -> str:
    final_filter = {}

    # --- STORAGE FILTER ---
    for storage_resource in storage_resources:
        storage_info = parse_storage_resource(storage_resource)
        storage_filter = build_storage_filter(storage_info)
        final_filter = merge_filters(final_filter, storage_filter)

    # --- COMPUTE FILTER ---
    for compute_resource in compute_resources:
        compute_info = parse_compute_resource(compute_resource)
        compute_filter = build_compute_filter(compute_info)
        final_filter = merge_filters(final_filter, compute_filter)

    # --- SERVICE FILTER ---
    for service_resource in service_resources:
        service_info = extract_service(service_resource)
        service_filter = build_service_filter(service_info)
        final_filter = merge_filters(final_filter, service_filter)

    # --- OS FILTER ---
    for os_resource in os_resources:
        os_info = extract_distro_and_version(os_resource)
        os_filter = build_os_filter(os_info)
        final_filter = merge_filters(final_filter, os_filter)

    # --- QOS FILTER ---
    for qos_value in qos_values:
        qos_info = parse_qos_value(qos_value)
        qos_filter = build_qos_filter(qos_info)
        final_filter = merge_filters(final_filter, qos_filter)

    response_string = "\nDynamic query filter: " + str(final_filter) + "\n"
    cursor = collection.find(final_filter)
    results = list(cursor)

    response_string += f"Number of matches: {len(results)}\n"
    for i, doc in enumerate(results, start=1):
        response_string += f"--- Document #{i} ---\n"
        response_string += f"{doc}\n"

    return response_string
