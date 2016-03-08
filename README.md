Data only image containing an entrypoint wrapper script for running the official [Datadog Agent image](https://www.github.com/DataDog/docker-dd-agent) in a Rancher environment.

    * Sets the reported hostname to the name of the host (from Rancher Metadata service)
    * Sets DataDog tags from Rancher host labels (from Rancher Metadata service)

#### Builds

[![Docker Pulls](https://img.shields.io/docker/pulls/janeczku/datadog-rancher-init.svg)](https://hub.docker.com/r/janeczku/datadog-rancher-init)

Trusted automated builds are [available from Docker Hub](https://hub.docker.com/r/janeczku/datadog-rancher-init).

#### Usage in Rancher Compose

```YAML
datadog-agent:
  image: docker-dd-agent
  restart: always
  environment:
    API_KEY: ${api_key}
    HOST_LABELS: ${host_labels}
  volumes:
    - /var/run/docker.sock:/var/run/docker.sock
    - /proc/:/host/proc/:ro
    - /sys/fs/cgroup/:/host/sys/fs/cgroup:ro
  volumes_from:
    - datadog-init
  entrypoint: /opt/rancher/entrypoint.sh
datadog-init:
  image: janeczku/datadog-rancher-init
  net: none
  command: /bin/true
  labels:
    io.rancher.container.start_once: 'true'
  volumes:
    - /opt/rancher
```