#!/bin/bash

set -e
DIR_NAME="$(dirname "$0")"
source "${DIR_NAME}/env.sh"

if [ $(uname) == "Darwin" ]; then
  docker buildx build \
    --build-arg PROJECT=${PROJECT} \
    --build-arg REPOSITORY=${REPOSITORY} \
    --platform linux/amd64,linux/arm64 \
    --tag "localhost/${PROJECT}:latest" \
    -f ./Dockerfile .
else
  docker build \
    --build-arg PROJECT=${PROJECT} \
    --build-arg REPOSITORY=${REPOSITORY} \
    --tag "localhost/${PROJECT}:latest" \
    -f ./Dockerfile .
fi

