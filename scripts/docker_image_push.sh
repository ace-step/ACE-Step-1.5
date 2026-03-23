#!/bin/bash

set -e
DIR_NAME="$(dirname "$0")"
source "${DIR_NAME}/env.sh"

docker tag "localhost/ace-step:latest" "asia-southeast1-docker.pkg.dev/bandlab-poc/ace-step/ace-step:latest"
docker tag "asia-southeast1-docker.pkg.dev/bandlab-poc/ace-step/ace-step:latest" "asia-southeast1-docker.pkg.dev/bandlab-poc/ace-step/ace-step:$GIT_COMMIT"

docker push "asia-southeast1-docker.pkg.dev/bandlab-poc/ace-step/ace-step:latest"
docker push "asia-southeast1-docker.pkg.dev/bandlab-poc/ace-step/ace-step:$GIT_COMMIT"

