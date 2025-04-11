#!/usr/bin/env sh
rasa run -m models --enable-api --cors "*";
#curl -X POST -H "Content-Type: application/json" -d '{"message": "start over"}' http://localhost:5005/webhooks/rest/webhook
