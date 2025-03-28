#!/usr/bin/env sh

docker run -d \
    --name my_mongo \
    -p 27017:27017 \
    -v ~/mongo_data:/data/db \
    mongo
