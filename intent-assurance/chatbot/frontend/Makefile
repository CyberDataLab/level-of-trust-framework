# Makefile for managing Flask Docker setup

build:
	docker build -t flask-app .

run:
	docker run --name web_app --network tfg_network -p 5000:5000 -v $(PWD):/app flask-app

stop:
	docker ps -q --filter "ancestor=flask-app" | xargs -r docker stop

clean:
	docker images -q flask-app | xargs -r docker rmi
