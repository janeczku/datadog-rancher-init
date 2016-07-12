[![Docker Pulls](https://img.shields.io/docker/pulls/janeczku/datadog-rancher-init.svg)](https://hub.docker.com/r/janeczku/datadog-rancher-init)

Image used in configuration sidekick container that provides better integration of the official [Datadog Agent image](https://www.github.com/DataDog/docker-dd-agent) with Rancher (Cattle and Kubernetes).

    * Correct naming of hosts in Datadog
    * Exports Rancher host and service labels as Datadog tags

#### Build the image

> make build

> make container
