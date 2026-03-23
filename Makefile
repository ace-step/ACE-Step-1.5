# note: call scripts from /scripts

.PHONY: docker
docker:
	./scripts/docker.sh

.PHONY: push
push:
	./scripts/docker_image_push.sh

%:
	@:


