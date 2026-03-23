#!/bin/bash

echo $GCR_CREDENTIALS | docker login -u _json_key --password-stdin https://asia-southeast1-docker.pkg.dev

