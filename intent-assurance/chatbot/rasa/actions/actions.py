# This files contains your custom actions which can be used to run
# custom Python code.
#
# See this guide on how to implement these action:
# https://rasa.com/docs/rasa/custom-actions

from typing import Any, Text, Dict, List
import json

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet

def flush_slots():
    return [SlotSet("service_assets_dict", ""), SlotSet("users", ""), SlotSet("tla_dict", "")]

# This is a simple example for a custom action which utters "Hello World!"
#
# class ActionHelloWorld(Action):
#
#     def name(self) -> Text:
#         return "action_hello_world"
#
#     def run(self, dispatcher: CollectingDispatcher,
#             tracker: Tracker,
#             domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
#
#         dispatcher.utter_message(text="Hello World!")
#
#         return []

""" Build actions """

# Action to extract the entities from the user intent "build"
class ActionBuild(Action):

    def name(self) -> Text:
        return "action_build"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        # Extract the entities from the user intent
        middlebox = list(tracker.get_latest_entity_values("middlebox"))
        assets = list(tracker.get_latest_entity_values("asset"))
        users = list(tracker.get_latest_entity_values("user"))

        # Show the middlebox and assets extracted
        dispatcher.utter_message("Building " + middlebox[0] + "...")
        if assets:
            dispatcher.utter_message("Using assets: ")
            for asset in assets:
                dispatcher.utter_message(asset)
        # Prepare the JSON for the service slot
        service_data = {
            "service": middlebox[0],
            "assets": assets
        }
        service_json = json.dumps(service_data)

        # Show the users extracted
        dispatcher.utter_message("Accessible to: ")
        for user in users:
            dispatcher.utter_message(user)
        # Prepare the JSON for the users slot
        user_data = {"users": users}
        users_json = json.dumps(user_data)

        # Update slots
        return [SlotSet("service_assets_dict", service_json), SlotSet("users", users_json)]
    
# Action to perform the deployment of the services built
class ActionDeploy(Action):

    def name(self) -> Text:
        return "action_deploy"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        dispatcher.utter_message(text="Deploying confirmed services...")

        json_data = json.loads(tracker.get_slot("service_assets_dict"))
        service = json_data["service"]
        assets = json_data["assets"]
        dispatcher.utter_message("Service " + service + " deployed with assets: ")
        for asset in assets:
            dispatcher.utter_message(asset)
        #TODO: Add deployment Ollama/LangChain logic here
        return flush_slots()

# Action to extract the entities from the user intent "build-feedback"
class ActionBuildFeedback(Action):

    def name(self) -> Text:
        return "action_build_feedback"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        last_message = tracker.latest_message.get('text')
        dispatcher.utter_message(f"Last message you said: {last_message}")
        dispatcher.utter_message(text="Action Build Feedback")

        return []

""" TLA actions """

# Action to extract the entities from the user intent "create_tla"
class ActionCreateTLA(Action):

    def name(self) -> Text:
        return "action_create_tla"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        # Extract the entities from the user intent
        user = list(tracker.get_latest_entity_values("user"))
        requirements = list(tracker.get_latest_entity_values("requirements"))

        # Show the user and requirements extracted
        dispatcher.utter_message("Creating TLA for user " + user[0] + " with requirements: ")
        for req in requirements:
            dispatcher.utter_message(req)
        
        tla_data = {
            "user": user[0],
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

""" Auxiliar actions """

# Action to start over the conversation and reset the slots
class ActionStartOver(Action):

    def name(self) -> Text:
        return "action_start_over"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        dispatcher.utter_message(text="Aborting current processes, let's start over, ask me anything!")

        return flush_slots()