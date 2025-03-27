# See this guide on how to implement these action:
# https://rasa.com/docs/rasa/custom-actions

from typing import Any, Text, Dict, List
import json

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet

# Constants
ADD_FEEDBACK_ACTION = "add"
REMOVE_FEEDBACK_ACTION = "remove"

# Global variables
build_classes = ["middlebox", "asset"]
tla_classes = ["requirements"]

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

    # 3) Buscamos en build_json un servicio con middlebox=="Unknown middlebox" que tenga esos assets
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

        # 1) Sort entities by their 'start' index to respect user’s text order
        sorted_entities = sorted(all_entities, key=lambda e: e.get("start", 0))

        # 2) Build a structure that groups each middlebox with its associated assets
        services = []
        current_service = None

        for ent in sorted_entities:
            entity_type = ent["entity"]
            entity_value = ent["value"]

            if entity_type == "middlebox":
                # If we were already tracking a service, store it before starting a new one
                if current_service:
                    services.append(current_service)

                # Start a new service entry for this middlebox
                current_service = {
                    "middlebox": entity_value,
                    "assets": []
                }

            elif entity_type == "asset":
                # If there's no current service yet, create one implicitly
                if not current_service:
                    current_service = {
                        "middlebox": None,
                        "assets": []
                    }
                current_service["assets"].append(entity_value)

        # Don't forget to save the last service
        if current_service:
            services.append(current_service)

        # 3) Generate a user-facing response
        response_lines = []
        for i, service in enumerate(services, start=1):
            mb = service["middlebox"] or "Unknown middlebox"
            line = f"Service {i}: {mb}"
            if service["assets"]:
                line += "\n  Using assets:"
                for asset in service["assets"]:
                    line += f"\n    - {asset}"
            response_lines.append(line)

        final_response = "\n\n".join(response_lines)
        dispatcher.utter_message(final_response)

        # Store these in a slot
        services_json = json.dumps(services)
        return [SlotSet("service_assets_dict", services_json), SlotSet("current_build_message", current_build_message)]
    
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