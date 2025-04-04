#!/usr/bin/env sh

docker container stop my_mongo && docker container rm my_mongo
docker run -d \
    --name my_mongo \
    -p 27017:27017 \
    -v ~/mongo_data:/data/db \
    mongo
