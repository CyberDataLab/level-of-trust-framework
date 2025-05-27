#!/bin/bash

/home/alfonso/kafka/bin/zookeeper-server-start.sh /home/alfonso/kafka/config/zookeeper.properties &
/home/alfonso/kafka/bin/kafka-server-start.sh /home/alfonso/kafka/config/server.properties &
