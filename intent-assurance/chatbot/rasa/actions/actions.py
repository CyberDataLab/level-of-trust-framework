# See this guide on how to implement these action:
# https://rasa.com/docs/rasa/custom-actions

from typing import Any, Text, Dict, List
import json
from . import mongo_helper as mh

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet

# Constants
ADD_FEEDBACK_OPERATION = "add"
REMOVE_FEEDBACK_OPERATION = "remove"

""" Helper functions """

def flush_slots():
    return [SlotSet("service_assets_dict", ""), SlotSet("tla_dict", ""),
             SlotSet("current_build_message", "")]

""" Feedback functions """

def add_asset_feedback(tracker, entity, value):
    # Ensure the slot value is a JSON string before parsing
    service_assets_slot = tracker.get_slot("service_assets_dict")
    if isinstance(service_assets_slot, list):
        build_json = service_assets_slot
    else:
        build_json = json.loads(service_assets_slot)
    print(f"Debug: Initial build_json: {json.dumps(build_json, indent=4)}")

    current_build_message_lower = tracker.get_slot("current_build_message").lower().split()
    print(f"Debug: Current build message: {current_build_message_lower}")

    value_lower = value.lower()
    middleboxes_lower = [service["middlebox"].lower() for service in build_json if service["middlebox"]]

    latest_middlebox = None

    # Identify the latest middlebox mentioned in the current build message
    for word in current_build_message_lower:
        if word in middleboxes_lower:
            idx = middleboxes_lower.index(word)
            latest_middlebox = build_json[idx]["middlebox"]
            print(f"Debug: Latest middlebox identified: {latest_middlebox}")

    # If a middlebox is identified, add the asset to its service
    if latest_middlebox:
        for service in build_json:
            if service["middlebox"].lower() == latest_middlebox.lower():
                # Check if the asset already exists
                asset_exists = any(asset["value"].lower() == value_lower for asset in service["assets"])
                if not asset_exists:
                    service["assets"].append({
                        "type": entity,
                        "value": value
                    })
                    print(f"Debug: Updated build_json after adding asset: {json.dumps(build_json, indent=4)}")
                    return build_json

    # If no middlebox is identified, fallback to adding the asset to the most recent service
    if build_json:
        most_recent_service = build_json[-1]
        print(f"Debug: Fallback to most recent service: {most_recent_service}")
        asset_exists = any(asset["value"].lower() == value_lower for asset in most_recent_service["assets"])
        if not asset_exists:
            most_recent_service["assets"].append({
                "type": entity,
                "value": value
            })
            print(f"Debug: Updated build_json after fallback: {json.dumps(build_json, indent=4)}")
            return build_json

    # If no suitable service is found, return None
    print("Debug: No suitable service found to add the asset.")
    return None

def add_middlebox_feedback(dispatcher, tracker, value):
    # Ensure the slot value is a JSON string before parsing
    service_assets_slot = tracker.get_slot("service_assets_dict")
    if isinstance(service_assets_slot, list):
        build_json = service_assets_slot
    else:
        build_json = json.loads(service_assets_slot)
    print(f"Debug: Initial build_json: {json.dumps(build_json, indent=4)}")

    current_build_message = tracker.get_slot("current_build_message")

    detected_middleboxes = [service["middlebox"] for service in build_json]
    detected_assets = [
        {
            "type": asset["type"],
            "value": asset["value"]
        }
        for service in build_json for asset in service["assets"]
    ]

    dispatcher.utter_message(f"Current build message: {current_build_message}")
    dispatcher.utter_message(f"build_json: {json.dumps(build_json, indent=4)}")

    # 1) Locate the position of the token identified as the middlebox
    new_middlebox_index = None
    for i, word in enumerate(current_build_message.split()):
        dispatcher.utter_message(f"Word: {word} - Value: {value}")
        if word.lower() == value.lower():
            new_middlebox_index = i
            dispatcher.utter_message(f"Match found at index {new_middlebox_index}")
            break

    if new_middlebox_index is None:
        dispatcher.utter_message("The token was not found in the message")
        return None

    # 2) Collect 'asset' entities from that position until encountering another middlebox
    desired_assets = []
    for j in range(new_middlebox_index + 1, len(current_build_message.split())):
        word = current_build_message.split()[j]
        if word in [mb.lower() for mb in detected_middleboxes]:
            # Stop if another middlebox is found
            break
        for asset in detected_assets:
            if word.lower() == asset["value"].lower():
                desired_assets.append(asset)

    # 3) Search for a service with middlebox == None that has these assets
    for service in build_json:
        if service["middlebox"] is None:
            # Check if the list of assets matches
            if all(asset in service["assets"] for asset in desired_assets):
                service["middlebox"] = value
                dispatcher.utter_message("Middlebox updated")
                print(json.dumps(build_json, indent=4))
                return build_json

    # 4) If no service with these assets is found, create a new one
    new_service = {
        "middlebox": value,
        "assets": desired_assets
    }
    build_json.append(new_service)
    dispatcher.utter_message("New service added")
    print(json.dumps(build_json, indent=4))
    return build_json

def remove_build_feedback(tracker, value, entity):
    build_json = json.loads(tracker.get_slot("service_assets_dict"))

    # Convertimos el valor a minúsculas para hacer la comparación
    value_lower = value.lower()

    # Debugging: Log the inputs and current state
    print(f"Debug: Received value='{value}', entity='{entity}'")
    print(f"Debug: Current build_json={json.dumps(build_json, indent=4)}")

    if entity == "middlebox" or entity in mh.BUILD_CLASSES or entity in mh.BUILD_CLASSES:
        for service in build_json:
            if service["middlebox"].lower() == value_lower:
                print(f"Debug: Found matching middlebox='{service['middlebox']}'")
                build_json.remove(service)
                # Return the updated build_json after removal
                print(json.dumps(build_json, indent=4))
                return build_json

    elif entity == "asset" or entity in mh.ASSET_CLASSES or entity in mh.TLA_CLASSES:
        for service in build_json:
            for asset in service["assets"]:
                if asset.get("value", "").lower() == value_lower:
                    print(f"Debug: Found matching asset='{asset}' in service='{service['middlebox']}'")
                    service["assets"].remove(asset)
                    print(json.dumps(build_json, indent=4))
                    return build_json

    # Debugging: Log if no match was found
    print(f"Debug: No match found for value='{value_lower}' and entity='{entity}'")
    return build_json  # Return the original build_json if no match is found

# Added debug messages to track slot updates and ensure JSON is not overridden

def process_feedback_output(dispatcher, tracker, new_json, action, entity, value):
    print(f"Debug: new_json after {action} operation: {json.dumps(new_json, indent=4) if new_json else 'None'}")

    # Ensure the new JSON is valid before updating the slot
    if new_json:
        dispatcher.utter_message(f"{action.capitalize()}d {entity}: {value}")
        print(f"Debug: Updating slot 'service_assets_dict' with: {new_json}")

        # Log the current slot value before updating
        current_slot_value = tracker.get_slot("service_assets_dict")
        print(f"Debug: Current slot value before update: {current_slot_value}")

        return [SlotSet("service_assets_dict", new_json)]
    else:
        dispatcher.utter_message("I couldn't apply the feedback. Please provide a valid entity and value.")
        print("Debug: Feedback operation failed. No changes made to the slot.")
        return []

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
                elif entity_type in mh.ASSET_CLASSES or entity_type in mh.TLA_CLASSES:
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

        storage_requirements = []
        service_requirements = []
        os_requirements = []
        compute_requirements = []
        qos_requirements = []

        for service in assets_dict:
            for asset in service.get("assets", []):
                asset_type = asset.get("type")
                asset_value = asset.get("value")

                if asset_type == "storage_resource":
                    storage_requirements.append(asset_value)
                elif asset_type == "service":
                    service_requirements.append(asset_value)
                elif asset_type == "operating_system":
                    os_requirements.append(asset_value)
                elif asset_type == "compute_resource":
                    compute_requirements.append(asset_value)
                elif asset_type == "qos_value":
                    qos_requirements.append(asset_value)

        result = mh.dynamic_query(
            storage_resources=storage_requirements,
            compute_resources=compute_requirements,
            os_resources=os_requirements,
            service_resources=service_requirements,
            qos_values=qos_requirements
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
        operation = next(tracker.get_latest_entity_values("operation"), None)

        dispatcher.utter_message(f"Received feedback: {value}-{entity}")
        if operation and operation.lower() == REMOVE_FEEDBACK_OPERATION:
            dispatcher.utter_message(f"\t\tOperation: {operation}")
            return process_feedback_output(dispatcher, tracker, remove_build_feedback(tracker, value, entity), REMOVE_FEEDBACK_OPERATION, entity, value)
        elif operation and operation.lower() == ADD_FEEDBACK_OPERATION:
            dispatcher.utter_message(f"\t\tOperation: {ADD_FEEDBACK_OPERATION}")
            # Check if the user wants to add an entity
            if entity == "middlebox" or entity in mh.BUILD_CLASSES or entity in mh.AVAILABLE_SERVICES:
                dispatcher.utter_message(f"\t\tOperation: {operation} another {entity}")
                return process_feedback_output(dispatcher, tracker, add_middlebox_feedback(dispatcher, tracker, value), ADD_FEEDBACK_OPERATION, entity, value)
            elif entity == "asset" or entity in mh.ASSET_CLASSES or entity in mh.TLA_CLASSES:
                dispatcher.utter_message(f"\t\tOperation: {operation} another {entity}")
                return process_feedback_output(dispatcher, tracker, add_asset_feedback(tracker, entity, value), ADD_FEEDBACK_OPERATION, entity, value)
            else:
                dispatcher.utter_message("I'm not sure what you're referring to. Please provide a valid entity.")
        else:
            dispatcher.utter_message("I couldn't understand the feedback. Please provide a valid entity and value.")
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
