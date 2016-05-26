[![Docker Pulls](https://img.shields.io/docker/pulls/janeczku/datadog-rancher-init.svg)](https://hub.docker.com/r/janeczku/datadog-rancher-init)

Image used for configuration sidekick container to run the official [Datadog Agent image](https://www.github.com/DataDog/docker-dd-agent) in Rancher (Cattle and Kubernetes).

    * Sets the reported hostname to the name of the host
    * Sets DataDog tags from Rancher host and container labels

#### Build the image

> make build

> make container
