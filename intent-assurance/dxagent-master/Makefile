#! /usr/bin/env make -f
.PHONY: containers dxagent dxcollector rm
# Makefile for dxagent

dxagent:
	cp .dockerignore.dxagent .dockerignore
	docker-compose -f docker-compose-dxagent.yml build
	docker-compose -f docker-compose-dxagent.yml up
dxcollector:
	cp .dockerignore.dxcollector .dockerignore
	docker-compose -f docker-compose-dxcollector.yml build
	docker-compose -f docker-compose-dxcollector.yml up

all:
	cp .dockerignore.all .dockerignore
	docker-compose -f docker-compose-all.yml build
	docker-compose -f docker-compose-all.yml up -d
rm:
	docker-compose -f docker-compose-dxagent.yml down
	docker-compose -f docker-compose-dxcollector.yml down
	docker-compose -f docker-compose-dxagent.yml rm
	docker-compose -f docker-compose-dxcollector.yml rm
