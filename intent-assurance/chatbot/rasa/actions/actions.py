# See this guide on how to implement these action:
# https://rasa.com/docs/rasa/custom-actions

from typing import Any, Text, Dict, List
import json
import re
from pymongo import MongoClient

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet

# Constants
ADD_FEEDBACK_ACTION = "add"
REMOVE_FEEDBACK_ACTION = "remove"

# Global variables
build_classes = ["middlebox"]
asset_classes = ["storage_resource", "compute_resource", "operating_system", "service"]
tla_classes = ["qos_value", "qos_unit"]

# Resource lists
CODENAME_MAP = {
    "xenial": "ubuntu",
    "noble": "ubuntu",
    "bionic": "ubuntu",
    "focal": "ubuntu",
    "jammy": "ubuntu",
}
AVAILABLE_DISTROS = ["ubuntu", "centos", "fedora", "windows"]
AVAILABLE_SERVICES = ["firewall", "load balancer", "ids", "ips", "proxy", "nat", "vpn", "voip", "dns", "directory"]
AVAILABLE_SERVICES_SOFTWARE = ["snort", "suricata", "pfsense", "openvswitch", "haproxy", "apache", "bind", "openldap", "asterisk"]

# MongoDB connection
client = MongoClient("mongodb://localhost:27017/")
db = client["example_database"]
collection = db["wef_entities"]

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
        "assets.virtualStorageDesc": {
            "$elemMatch": {
                "sizeOfStorage": size,
                "sizeOfStorageUnit": unit
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

    ram_pattern = re.compile(r'(\d+(?:\.\d+)?)\s*([KkMmGgTt]b)', re.IGNORECASE)
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
        "assets.virtualComputeDesc": {
            "$elemMatch": {
                "$and": conditions
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
    

#Function to build the MongoDB query for a service resource
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

# Function to merge two MongoDB query filters
def merge_filters(filter1: dict, filter2: dict) -> dict:
    if not filter1:
        return filter2
    if not filter2:
        return filter1
    return {
        "$and": [filter1, filter2]
    }
   
# Function to perform a dynamic query on the MongoDB
def dynamic_query(storage_resource, compute_resource,
                  os_resource, service_resource) -> str:
    final_filter = {}

    # --- STORAGE FILTER ---
    if storage_resource:
        storage_info = parse_storage_resource(storage_resource)
        storage_filter = build_storage_filter(storage_info)
        final_filter = merge_filters(final_filter, storage_filter)

    # --- COMPUTE FILTER ---
    if compute_resource:
        compute_info = parse_compute_resource(compute_resource)
        compute_filter = build_compute_filter(compute_info)
        final_filter = merge_filters(final_filter, compute_filter)

    # --- SERVICE FILTER ---
    if service_resource:
        service_info = extract_service(service_resource)
        service_filter = build_service_filter(service_info)
        final_filter = merge_filters(final_filter, service_filter)

    # --- OS FILTER ---
    if os_resource:
        os_info = extract_distro_and_version(os_resource)
        os_filter = build_os_filter(os_info)
        final_filter = merge_filters(final_filter, os_filter)

    response_string = "\nDynamic query filter: " + str(final_filter) + "\n"
    cursor = collection.find(final_filter)
    results = list(cursor)

    response_string += f"Number of matches: {len(results)}\n"
    for i, doc in enumerate(results, start=1):
        response_string += f"--- Document #{i} ---\n"
        response_string += f"{doc}\n"

    return response_string
        
""" Helper functions """

def flush_slots():
    return [SlotSet("service_assets_dict", ""), SlotSet("tla_dict", ""),
             SlotSet("current_build_message", "")]

""" Feedback functions """

def add_asset_feedback(tracker, value):
    build_json = json.loads(tracker.get_slot("service_assets_dict"))

    # Convertimos el mensaje actual y el valor buscado a minúsculas
    current_build_message_lower = tracker.get_slot("current_build_message").lower().split()
    value_lower = value.lower()

    # Construimos una lista de middleboxes en minúsculas para comparaciones
    middleboxes_lower = [service["middlebox"].lower() for service in build_json]

    latest_middlebox = None

    for word in current_build_message_lower:
        if word in middleboxes_lower:
            idx = middleboxes_lower.index(word)
            latest_middlebox = build_json[idx]["middlebox"]
            continue

        if word == value_lower and latest_middlebox is not None:
            for service in build_json:
                if service["middlebox"].lower() == latest_middlebox.lower():
                    service["assets"].append(value)
                    return build_json

    return None

def add_middlebox_feedback(dispatcher, tracker, value):
    build_json = json.loads(tracker.get_slot("service_assets_dict"))
    current_build_message = tracker.get_slot("current_build_message")

    detected_middleboxes = [service["middlebox"] for service in build_json]
    detected_assets = [asset for service in build_json for asset in service["assets"]]

    dispatcher.utter_message(f"Current build message: {current_build_message}")
    dispatcher.utter_message(f"build_json: {json.dumps(build_json, indent=4)}")

    # 1) Localizamos la posición del token que se indicó cómo middlebox
    new_middlebox_index = None
    i = 0
    for i, word in enumerate(current_build_message.split()):
        dispatcher.utter_message(f"Word: {word} - Value: {value}")
        if word.lower() == value.lower():
            new_middlebox_index = i
            dispatcher.utter_message(f"Match found at index {new_middlebox_index}")
            break

    if new_middlebox_index is None:
        dispatcher.utter_message("No se encontró el token en el mensaje")
        return None

    # 2) A partir de esa posición, recolectamos las entidades de tipo 'asset' hasta toparte con otro middlebox
    desired_assets = []
    for j in range(new_middlebox_index + 1, len(current_build_message.split())):
        word = current_build_message.split()[j]
        if word in detected_middleboxes:
            # Si encontramos otro middlebox, paramos
            break
        elif word in detected_assets:
            desired_assets.append(word)

    # 3) Buscamos en build_json un servicio con middlebox=="null" que tenga esos assets
    for service in build_json:
        if service["middlebox"] == None:
            # Comprobamos si coincide la lista de assets
            if service["assets"] == desired_assets:
                service["middlebox"] = value
                dispatcher.utter_message("Middlebox updated")
                dispatcher.utter_message(json.dumps(build_json, indent=4))
                return build_json

    # 4) Si no encontramos un servicio con esos assets, creamos uno nuevo
    new_service = {
        "middlebox": value,
        "assets": []
    }
    build_json.append(new_service)
    dispatcher.utter_message("New service added")
    dispatcher.utter_message(json.dumps(build_json, indent=4))
    return build_json

import json

def remove_build_feedback(tracker, value, entity):
    build_json = json.loads(tracker.get_slot("service_assets_dict"))

    # Convertimos el valor a minúsculas para hacer la comparación
    value_lower = value.lower()

    if entity == "middlebox":
        for service in build_json:
            if service["middlebox"].lower() == value_lower:
                build_json.remove(service)
                return build_json

    elif entity == "asset":
        for service in build_json:
            for asset in service["assets"]:
                if asset.lower() == value_lower:
                    service["assets"].remove(asset)
                    return build_json

    return None


def add_tla_feedback(tracker, value):
    tla_json = json.loads(tracker.get_slot("tla_dict"))
    requirements = tla_json["requirements"]
    if value not in requirements:
        requirements.append(value)
        return tla_json
    return None

def remove_tla_feedback(tracker, value):
    tla_json = json.loads(tracker.get_slot("tla_dict"))
    requirements = tla_json["requirements"]
    if value in requirements:
        requirements.remove(value)
        return tla_json
    return None

def process_feedback_output(dispatcher, new_json, action, entity, value):
    if not new_json:
        dispatcher.utter_message("I couldn't apply the feedback. Please provide a valid entity and value.")
        return []
    else:
        dispatcher.utter_message(f"{action.capitalize()}ed {entity}: {value}")
        return [SlotSet("service_assets_dict", json.dumps(new_json))]

""" Build actions """

# Action to extract the entities from the user intent "build"
class ActionBuild(Action):

    def name(self) -> Text:
        return "action_build"

    def run(self, dispatcher: CollectingDispatcher,
                tracker: Tracker,
                domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

            dispatcher.utter_message("Analyzing intent...")
            current_build_message = tracker.latest_message.get('text')
            # Get all entities with their positions in the user message
            all_entities = tracker.latest_message.get("entities", [])

            # 1) Sort entities by their 'start' index to respect the user’s text order
            sorted_entities = sorted(all_entities, key=lambda e: e.get("start", 0))

            # 2) Build a structure that groups each middlebox with its associated assets
            services = []
            current_service = None

            for ent in sorted_entities:
                entity_type = ent["entity"]
                entity_value = ent["value"]

                # If the user message indicates a new middlebox, start a new service
                if entity_type == "middlebox":
                    # If we were already tracking a service, store it before starting a new one
                    if current_service:
                        services.append(current_service)

                    # Start a fresh service entry for this middlebox
                    current_service = {
                        "middlebox": entity_value,
                        "assets": []
                    }

                # Otherwise check if the entity is one of the four recognized asset classes
                elif entity_type in asset_classes:
                    # If there's no current service yet, create one implicitly
                    if not current_service:
                        current_service = {
                            "middlebox": None,
                            "assets": []
                        }

                    current_service["assets"].append({
                        "type": entity_type,
                        "value": entity_value
                    })

            # Don't forget to add the last service if we have one in progress
            if current_service:
                services.append(current_service)

            # 3) Generate a user-facing response summarizing what was captured
            response_lines = []
            for i, service in enumerate(services, start=1):
                mb = service["middlebox"] or "Unknown middlebox"
                line = f"Service {i}: {mb}"
                if service["assets"]:
                    line += "\n  Using assets:"
                    for asset_obj in service["assets"]:
                        line += f"\n    - {asset_obj['type']}: {asset_obj['value']}"
                response_lines.append(line)

            final_response = "\n\n".join(response_lines)
            dispatcher.utter_message(final_response)

            # Store in slots for further usage
            services_json = json.dumps(services)
            return [
                SlotSet("service_assets_dict", services_json),
                SlotSet("current_build_message", current_build_message)
            ]

# Action to check the availability of the middleboxes and assets
class ActionCheckAvailability(Action):
    def name(self) -> Text:
        return "action_check_avaibility"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        assets_dict = json.loads(tracker.get_slot("service_assets_dict"))

        storage_example = None
        service_example = None
        os_example = None
        compute_example = None

        for service in assets_dict:
            for asset in service.get("assets", []):
                asset_type = asset.get("type")
                asset_value = asset.get("value")

                if asset_type == "storage_resource" and not storage_example:
                    storage_example = asset_value
                elif asset_type == "service" and not service_example:
                    service_example = asset_value
                elif asset_type == "operating_system" and not os_example:
                    os_example = asset_value
                elif asset_type == "compute_resource" and not compute_example:
                    compute_example = asset_value

                # Stop early if we have all types
                if all([storage_example, service_example, os_example, compute_example]):
                    break
            if all([storage_example, service_example, os_example, compute_example]):
                break

        # Safety: fallback message if some are missing
        if not any([storage_example, service_example, os_example, compute_example]):
            dispatcher.utter_message("No suitable asset types found to perform the query.")
            return []

        result = dynamic_query(
            storage_resource=storage_example,
            compute_resource=compute_example,
            os_resource=os_example,
            service_resource=service_example
        )

        dispatcher.utter_message(result)
        return []  

# Action to perform the deployment of the services built
class ActionDeploy(Action):

    def name(self) -> Text:
        return "action_deploy"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        try:
            services = json.loads(tracker.get_slot("service_assets_dict"))
        except json.JSONDecodeError:
            return "I couldn't understand the services data."

        response_lines = []
        for i, service in enumerate(services, start=1):
            middlebox = service.get("middlebox", "unknown middlebox")
            assets = service.get("assets", [])

            # Start with a brief summary of the middlebox
            line = f"For service #{i}, we're deploying a '{middlebox}'."
            
            # If there are assets associated with this middlebox, show them
            if assets:
                line += " It will have the following assets:\n"
                for asset in assets:
                    line += f"  - {asset}\n"
            else:
                line += " No specific assets were mentioned.\n"
            
            response_lines.append(line)

        response = "\n".join(response_lines)
        dispatcher.utter_message(response)

        #TODO: Add deployment Ollama/LangChain logic here
        
        return flush_slots()

# Action to extract the entities from the user intent "feedback"
class ActionBuildFeedback(Action):

    def name(self) -> Text:
        return "action_build_feedback"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        value = next(tracker.get_latest_entity_values("value"), None)
        entity = next(tracker.get_latest_entity_values("entity"), None)
        action = next(tracker.get_latest_entity_values("action"), None)

        dispatcher.utter_message(f"Received feedback: {value}-{entity}")

        if not value or not entity:
            dispatcher.utter_message("I couldn't understand the feedback. Please provide a valid entity and value.")
            return []

        # Check if the user wants to add an entity
        if entity == "middlebox":
            return process_feedback_output(dispatcher, add_middlebox_feedback(dispatcher, tracker, value), ADD_FEEDBACK_ACTION, entity, value)
        elif entity == "asset":
            return process_feedback_output(dispatcher, add_asset_feedback(tracker, value), ADD_FEEDBACK_ACTION, entity, value)
        else:
            dispatcher.utter_message("I'm not sure what you're referring to. Please provide a valid entity.")
        
        # Check if the user wants to remove an entity
        if action.lower == REMOVE_FEEDBACK_ACTION:
            return process_feedback_output(dispatcher, remove_build_feedback(tracker, value, entity), REMOVE_FEEDBACK_ACTION, entity, value)

        return []

""" TLA actions """

# Action to extract the entities from the user intent "create_tla"
class ActionCheckTLA(Action):

    def name(self) -> Text:
        return "action_check_tla"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        # Extract the entities from the user intent
        requirements = list(tracker.get_latest_entity_values("requirements"))

        # Show the user and requirements extracted
        response = "Checking feasability of TLA...\n Requirements:\n "
        dispatcher.utter_message("Checking feasability of TLA...\n Requirements:\n ")
        for req in requirements:
            response += req + "\n"
        dispatcher.utter_message(response)
        
        tla_data = {
            "requirements": requirements
        }
        tla_json = json.dumps(tla_data)

        return [SlotSet("tla_dict", tla_json)]
    
# Action to provide feedback on the TLA requirements
class ActionTLAFeedback(Action):

    def name(self) -> Text:
        return "action_tla_feedback"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        value = next(tracker.get_latest_entity_values("value"), None)
        entity = next(tracker.get_latest_entity_values("entity"), None)
        action = next(tracker.get_latest_entity_values("action"), None)

        dispatcher.utter_message(f"Received feedback: {value}-{entity}")

        if not value or not entity:
            dispatcher.utter_message("I couldn't understand the feedback. Please provide a valid entity and value.")
            return []
        
        if action.lower() == REMOVE_FEEDBACK_ACTION:
            return process_feedback_output(dispatcher, remove_tla_feedback(tracker, value), REMOVE_FEEDBACK_ACTION, entity, value)

        if entity == "requirements":
            return process_feedback_output(dispatcher, add_tla_feedback(tracker, value), ADD_FEEDBACK_ACTION, entity, value)
        else:
            dispatcher.utter_message("I'm not sure what you're referring to. Please provide a valid entity.")

        return []

# Action to handoff the TLA requirements to the next stage
class ActionPassTLA(Action):

    def name(self) -> Text:
        return "action_pass_tla"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        json_data = json.loads(tracker.get_slot("tla_dict"))
        requirements = json_data["requirements"]
        response = "Passing TLA with the following requirements:\n "
        for req in requirements:
            response += req + "\n"
        dispatcher.utter_message(response)

        return []