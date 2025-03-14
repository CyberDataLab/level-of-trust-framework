# See this guide on how to implement these action:
# https://rasa.com/docs/rasa/custom-actions

from typing import Any, Text, Dict, List
import json

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet

def flush_slots():
    return [SlotSet("service_assets_dict", ""), SlotSet("tla_dict", "")]

""" Build actions """

# Action to extract the entities from the user intent "build"
class ActionBuild(Action):

    def name(self) -> Text:
        return "action_build"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        dispatcher.utter_message("Analyzing intent...")
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
        # Show each middlebox and the assets specifically associated with it
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
        return [SlotSet("service_assets_dict", services_json)]
    
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

# Action to extract the entities from the user intent "build-feedback"
class ActionBuildFeedback(Action):

    def name(self) -> Text:
        return "action_build_feedback"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        value = tracker.get_latest_entity_values("value")
        entity = tracker.get_latest_entity_values("entity")
        dispatcher.utter_message(f"Feedback received: {value} for {entity}")

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
    
class ActionTLAFeedback(Action):

    def name(self) -> Text:
        return "action_tla_feedback"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        last_message = tracker.latest_message.get('text')
        dispatcher.utter_message(f"Last message you said: {last_message}")
        dispatcher.utter_message(text="Action TLA Feedback")

        return []

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