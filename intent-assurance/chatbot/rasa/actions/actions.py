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

# Initialize MongoDB connection
mh.initialize()

""" Helper functions """

def _flush_slots():
    return [SlotSet("service_assets_dict", ""), SlotSet("tla_dict", ""),
             SlotSet("current_build_message", ""), SlotSet("feedback_performed", False)]

def _save_feedback(tracker):
    build_message = tracker.get_slot("current_build_message")
    service_assets_slot = tracker.get_slot("service_assets_dict")

    # Parse service_assets_slot if it's a string
    if isinstance(service_assets_slot, str):
        try:
            service_assets_slot = json.loads(service_assets_slot)
        except json.JSONDecodeError:
            print("Error: Unable to parse service_assets_slot.")
            return

    build_message_words = build_message.split()
    updated_message = []

    for word in build_message_words:
        replaced = False
        # Check if the word matches a middlebox
        for service in service_assets_slot:
            if word.lower() == service["middlebox"].lower():
                updated_message.append(f"[{word}](middlebox)")
                replaced = True
                break
            for asset in service["assets"]:
                if word.lower() == asset["value"].lower():
                    updated_message.append(f"[{word}]({asset['type']})")
                    replaced = True
                    break
        if replaced:
            continue

        # Check if the word matches an asset
        for service in service_assets_slot:
            for asset in service["assets"]:
                if word.lower() == asset["value"].lower():
                    updated_message.append(f"[{word}]({asset['type']})")
                    replaced = True
                    break
            if replaced:
                break

        # If no match, keep the word as is
        if not replaced:
            updated_message.append(word)

    feedback_message = "- " + " ".join(updated_message)
    with open("feedback.yml", "a") as feedback_file:
        feedback_file.write(feedback_message + "\n")
    print(f"Debug: Feedback message saved: {feedback_message}")
    return feedback_message

""" Feedback functions """

def add_asset_feedback(tracker, entity, value) -> str:
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

    for word in current_build_message_lower:
        if word in middleboxes_lower:
            idx = middleboxes_lower.index(word)
            latest_middlebox = build_json[idx]["middlebox"]
            print(f"Debug: Latest middlebox identified: {latest_middlebox}")

    if latest_middlebox:
        for service in build_json:
            if service["middlebox"].lower() == latest_middlebox.lower():
                asset_exists = any(asset["value"].lower() == value_lower for asset in service["assets"])
                if not asset_exists:
                    service["assets"].append({
                        "type": entity,
                        "value": value
                    })
                    print(f"Debug: Updated build_json after adding asset: {json.dumps(build_json, indent=4)}")
                    return json.dumps(build_json)

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
            return json.dumps(build_json)

    print("Debug: No suitable service found to add the asset.")
    return json.dumps(build_json)

def add_middlebox_feedback(dispatcher, tracker, value) -> str:
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

    new_middlebox_index = None
    for i, word in enumerate(current_build_message.split()):
        dispatcher.utter_message(f"Word: {word} - Value: {value}")
        if word.lower() == value.lower():
            new_middlebox_index = i
            dispatcher.utter_message(f"Match found at index {new_middlebox_index}")
            break

    if new_middlebox_index is None:
        dispatcher.utter_message("The token was not found in the message")
        return json.dumps(build_json)

    desired_assets = []
    for j in range(new_middlebox_index + 1, len(current_build_message.split())):
        word = current_build_message.split()[j]
        if word in [mb.lower() for mb in detected_middleboxes]:
            break
        for asset in detected_assets:
            if word.lower() == asset["value"].lower():
                desired_assets.append(asset)

    for service in build_json:
        if service["middlebox"] is None:
            if all(asset in service["assets"] for asset in desired_assets):
                service["middlebox"] = value
                dispatcher.utter_message("Middlebox updated")
                print(json.dumps(build_json, indent=4))
                return json.dumps(build_json)

    new_service = {
        "middlebox": value,
        "assets": desired_assets
    }
    build_json.append(new_service)
    dispatcher.utter_message("New service added")
    print(json.dumps(build_json, indent=4))
    return json.dumps(build_json)

def remove_build_feedback(tracker, value, entity) -> str:
    build_json = json.loads(tracker.get_slot("service_assets_dict"))

    value_lower = value.lower()

    print(f"Debug: Received value='{value}', entity='{entity}'")
    print(f"Debug: Current build_json={json.dumps(build_json, indent=4)}")

    if entity == "middlebox" or entity in mh.BUILD_CLASSES:
        for service in build_json:
            if service["middlebox"].lower() == value_lower:
                print(f"Debug: Found matching middlebox='{service['middlebox']}'")
                build_json.remove(service)
                print(json.dumps(build_json, indent=4))
                return json.dumps(build_json)

    elif entity == "asset" or entity in mh.ASSET_CLASSES or entity in mh.TLA_CLASSES:
        for service in build_json:
            for asset in service["assets"]:
                if asset.get("value", "").lower() == value_lower:
                    print(f"Debug: Found matching asset='{asset}' in service='{service['middlebox']}'")
                    service["assets"].remove(asset)
                    print(json.dumps(build_json, indent=4))
                    return json.dumps(build_json)

    print(f"Debug: No match found for value='{value_lower}' and entity='{entity}'")
    return json.dumps(build_json)

def process_feedback_output(dispatcher, tracker, new_json, action, entity, value):
    print(f"Debug: new_json after {action} operation: {new_json}")

    if new_json:
        dispatcher.utter_message(f"{action.capitalize()}d {entity}: {value}")
        print(f"Debug: Updating slot 'service_assets_dict' with: {new_json}")

        current_slot_value = tracker.get_slot("service_assets_dict")
        print(f"Debug: Current slot value before update: {current_slot_value}")

        return [SlotSet("service_assets_dict", new_json), SlotSet("feedback_performed", True)]
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
                # Use the original token from the user message instead of the canonicalized value
                entity_value = current_build_message[ent["start"]:ent["end"]]

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
                SlotSet("current_build_message", current_build_message),
                SlotSet("feedback_performed", False)
            ]

# Action to check the availability of the middleboxes and assets
class ActionCheckAvailability(Action):
    def name(self) -> Text:
        return "action_check_avaibility"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        service_assets_slot = tracker.get_slot("service_assets_dict")

        if isinstance(service_assets_slot, list):
            assets_dict = service_assets_slot
        elif isinstance(service_assets_slot, str):
            try:
                assets_dict = json.loads(service_assets_slot)
            except json.JSONDecodeError:
                dispatcher.utter_message("Error: Unable to parse service assets slot.")
                return []
        else:
            dispatcher.utter_message("Error: The service assets slot is in an unexpected format.")
            return []
        
        if tracker.get_slot("feedback_performed") == True:
            print("Feedback performed, saving to database")
            _save_feedback(tracker)

        storage_requirements = []
        service_requirements = []
        os_requirements = []
        compute_requirements = []
        qos_requirements = []

        for service in assets_dict:
            middlebox = service.get("middlebox")
            if middlebox:
                service_requirements.append(middlebox)
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

        if not result or "Number of matches: 0" in result:
            dispatcher.utter_message("No matches found for the requested build parameters.")
            return [SlotSet("feedback_performed", False)]

        dispatcher.utter_message(result)
        return _flush_slots()

# Action to perform the deployment of the services built
class ActionDeploy(Action):

    def name(self) -> Text:
        return "action_deploy"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        services = None
        service_assets_slot = tracker.get_slot("service_assets_dict")
        if isinstance(service_assets_slot, str):
            try:
                services = json.loads(service_assets_slot)
            except json.JSONDecodeError:
                dispatcher.utter_message("Error: Unable to parse service assets slot.")
            return []

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
                line += f"  - {asset['type']}: {asset['value']}\n"
            else:
                line += " No specific assets were mentioned.\n"
            
            response_lines.append(line)

        response = "\n".join(response_lines)
        dispatcher.utter_message(response)

        #TODO: Add deployment Ollama/LangChain logic here
        
        return _flush_slots()

# Action to extract the entities from the user intent "feedback"
class ActionBuildFeedback(Action):

    def name(self) -> Text:
        return "action_build_feedback"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        entity = next((entity for entity in (mh.BUILD_CLASSES + mh.ASSET_CLASSES + mh.TLA_CLASSES) if tracker.get_latest_entity_values(entity)), None)
        value = next(tracker.get_latest_entity_values(entity), None) if entity else None
        operation = next(tracker.get_latest_entity_values("operation"), None)

        if not value or not entity:
            dispatcher.utter_message("I couldn't understand the feedback. Please provide a valid entity and value.")
            return []

        dispatcher.utter_message(f"Received feedback: {value}-{entity}")
        if operation and operation.lower() == REMOVE_FEEDBACK_OPERATION:
            dispatcher.utter_message(f"\t\tOperation: {operation}")
            return process_feedback_output(dispatcher, tracker, remove_build_feedback(tracker, value, entity), REMOVE_FEEDBACK_OPERATION, entity, value)
        elif operation and operation.lower() == ADD_FEEDBACK_OPERATION:
            dispatcher.utter_message(f"\t\tOperation: {ADD_FEEDBACK_OPERATION}")
            # Check if the user wants to add an entity
            if entity == "middlebox" or entity in mh.BUILD_CLASSES or entity in mh.available_services:
                dispatcher.utter_message(f"\t\tOperation: {operation} another {entity}")
                return process_feedback_output(dispatcher, tracker, add_middlebox_feedback(dispatcher, tracker, value), ADD_FEEDBACK_OPERATION, entity, value)
            elif entity == "asset" or entity in mh.ASSET_CLASSES or entity in mh.TLA_CLASSES:
                dispatcher.utter_message(f"\t\tOperation: {operation} another {entity}")
                return process_feedback_output(dispatcher, tracker, add_asset_feedback(tracker, entity, value), ADD_FEEDBACK_OPERATION, entity, value)
            else:
                dispatcher.utter_message("I'm not sure what you're referring to. Please provide a valid entity.")
        else:
            dispatcher.utter_message("I couldn't understand the feedback. Please provide a valid entity and value.")
        return [SlotSet("feedback_performed", False)]

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
