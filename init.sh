#!/usr/bin/env bash

mkdir secrets
echo "xxx" > secrets/MAPILLARY_CLIENT_TOKEN
echo "yyy" > secrets/firebase_credentials
docker volume create pics
