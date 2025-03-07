# This files contains your custom actions which can be used to run
# custom Python code.
#
# See this guide on how to implement these action:
# https://rasa.com/docs/rasa/custom-actions


# This is a simple example for a custom action which utters "Hello World!"

from typing import Any, Text, Dict, List

import json

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet

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
    
class ActionDeploy(Action):

    def name(self) -> Text:
        return "action_deploy"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        dispatcher.utter_message(text="Deploying confirmed services...")
        #TODO: Add deployment Ollama/LangChain logic here
        return []

class ActionFeedback(Action):

    def name(self) -> Text:
        return "action_feedback"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        dispatcher.utter_message(text="Hello World!")

        return []
    
class ActionFeedbackConfirm(Action):

    def name(self) -> Text:
        return "action_feedback_confirm"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        dispatcher.utter_message(text="Hello World!")

        return []