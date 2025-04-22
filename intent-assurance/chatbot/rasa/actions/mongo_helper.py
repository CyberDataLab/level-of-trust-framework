from pymongo import MongoClient
import re

UNIT_MAPPING = {
    "Bps": "bps",
    "KBps": "Kbps",
    "MBps": "Mbps",
    "GBps": "Gbps",
    "TBps": "Tbps"
}

# Entity classes
BUILD_CLASSES = ["middlebox"]
ASSET_CLASSES = ["storage_resource", "compute_resource", "operating_system", "service"]
TLA_CLASSES = ["qos_value"]

# Resource lists
codename_mapping = {}
available_flavors = [] #["server", "desktop", "headless", "cloud", "core", "minimal", "kubernetes", "container"]
available_distros = []
available_services = [] #"firewall", "load balancer", "ids", "ips", "proxy", "nat", "vpn", "voip", "dns", "directory"]
available_service_softwares = [] #["snort", "suricata", "pfsense", "openvswitch", "haproxy", "apache", "bind", "openldap", "asterisk"]

# MongoDB connection
client = None
db = None
collection = None

# Function to convert from Bps to bps
def _to_bitspersecond(value: str, unit: str) -> dict:

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

# Function to load the available os from the database
def _initialize_distros_lists():
    global available_distros, available_flavors
    
    osv_strings = []
    codenames = []
    cursor = collection.find({})

    for document in cursor:
        for asset in document["assets"]:
            if asset.get("type") == "resource" and "swImageDesc" in asset:
                osv_strings.append(asset["swImageDesc"]["operatingSystemVersion"].lower())
                codenames.append(asset["swImageDesc"].get("operatingSystemCodename", "").lower() if "operatingSystemCodename" in asset["swImageDesc"] else None)

    for osv_string, codename in zip(osv_strings, codenames):
        distro_flavor_pattern = re.compile(r'([a-z]+)(?:-([a-z]+))?', re.IGNORECASE)
        distro_flavor_match = distro_flavor_pattern.search(osv_string)
        if distro_flavor_match:
            available_distros.append(distro_flavor_match.group(1))
            available_flavors.append(distro_flavor_match.group(2))
            if codename:
                codename_mapping[codename] = distro_flavor_match.group(1)

    print("Updated available_distros:", available_distros)
    print("Updated available_flavors:", available_flavors)
    print("Updated codename_mapping:", codename_mapping)

# Function to load the available services from the database
def _initialize_services_lists():
    global available_services, available_service_softwares

    cursor = collection.find({})

    for document in cursor:
        for asset in document["assets"]:
            if asset.get("type") == "service" and "serviceDesc" in asset:
                service_desc = asset["serviceDesc"]

                service_type = service_desc.get("type")
                if service_type and service_type not in available_services:
                    available_services.append(service_type)

                service_software = service_desc.get("serviceSW")
                if service_software and service_software not in available_service_softwares:
                    available_service_softwares.append(service_software)
            
            # Process subservices
            if "subservices" in asset:
                for subservice in asset["subservices"]:
                    if "subserviceDesc" in subservice:
                        subservice_desc = subservice["subserviceDesc"]

                        # Extract subservice type
                        subservice_type = subservice_desc.get("type")
                        if subservice_type and subservice_type not in available_services:
                            available_services.append(subservice_type)

                        # Extract subservice software
                        subservice_software = subservice_desc.get("subserviceSW")
                        if subservice_software and subservice_software not in available_service_softwares:
                            available_service_softwares.append(subservice_software)

    print("Updated available_services:", available_services)
    print("Updated available_service_softwares:", available_service_softwares)

# Initialization function
def initialize():
    global client, db, collection
    client = MongoClient("mongodb://localhost:27017/")
    db = client["example_database"]
    collection = db["wef_entities"]
    _initialize_distros_lists()
    _initialize_services_lists()
    print("Initialization complete.")

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
    for t in available_services:
        if t in service_lower:
            result["type"] = t
            break

    # Identify known software
    for sw in available_service_softwares:
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

    for codename, mapped_distro in codename_mapping.items():
        if codename in os_lower:
            result["codename"] = codename
            result["distro"] = mapped_distro
            break 

    for flavor in available_flavors:
        if flavor in os_lower:
            result["flavor"] = flavor
            break

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
    qos_info = _to_bitspersecond(qos_info["value"], qos_info["unit"])
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

    if "$or" in filter1 and "$or" in filter2:
        return {
            "$or": filter1["$or"] + filter2["$or"]
        }
    elif "$or" in filter1:
        return {
            "$or": filter1["$or"] + [filter2]
        }
    elif "$or" in filter2:
        return {
            "$or": [filter1] + filter2["$or"]
        }
    else:
        return {
            "$or": [filter1, filter2]
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
