#!/bin/bash
set -e

export BUILD_TIME="$(date -u +%Y-%m-%d-%H-%M-%S)"
export GIT_BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null | tr A-Z a-z)"
export GIT_COMMIT="$(git rev-parse HEAD 2>/dev/null)"
export PROJECT="ace-step"
export REPOSITORY="github.com/bandlab/${PROJECT}"

