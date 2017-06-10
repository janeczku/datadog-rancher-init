#!/opt/datadog-agent/embedded/bin/python
'''
	Rancher sidekick entrypoint wrapper for datadog/docker-dd-agent
	Used in Datadog Rancher Catalog stack for Cattle and Kubernetes environments

	Configuration passed via environment variables:
	DD_SERVICE_DISCOVERY - whether to enable service discovery (true|false)
	DD_SD_CONFIG_BACKEND - configuration backend for service discovery (none|etcd|consul)
	DD_SD_BACKEND_HOST - backend host
	DD_SD_BACKEND_PORT - backend port
	DD_SD_TEMPLATE_DIR - overwrite default config template directory
	DD_CONSUL_TOKEN - Consul ACL token granting read access to the configuration template path
	DD_CONSUL_SCHEME - Scheme used to connect to Consul store (http|https)
	DD_CONSUL_VERIFY - Whether to verify the SSL certificate for HTTPS requests (true|false)
	DD_HOST_TAGS - comma seperated list of tags applied globally to all hosts
	DD_HOST_LABELS - comma seperated list of host labels to export as Datadog host tags
	DD_CONTAINER_LABELS - comma seperated list of container labels to export as Datadog metric tags
	DD_KUBERNETES - if set, skips export of container labels as tags
	DD_METADATA_HOSTNAME - hostname used to query Rancher's metadata service, default: rancher-metadata
	----
	Copyright (c) 2016-2017 Rancher Labs, Inc.
	Licensed under the Apache License, Version 2.0 (see LICENSE)
	
'''

import requests
import time
import re
import json
import os
import sys

# ENVIRONMENT VARIABLE NAMES
ENV_SD_ENABLED       = "DD_SERVICE_DISCOVERY"
ENV_SD_BACKEND_TYPE  = "DD_SD_CONFIG_BACKEND"
ENV_SD_BACKEND_HOST  = "DD_SD_BACKEND_HOST"
ENV_SD_BACKEND_PORT  = "DD_SD_BACKEND_PORT"
ENV_SD_TEMPLATE_DIR  = "DD_SD_TEMPLATE_DIR"
ENV_SD_CONSUL_TOKEN  = "DD_CONSUL_TOKEN"
ENV_SD_CONSUL_SCHEME = "DD_CONSUL_SCHEME"
ENV_SD_CONSUL_VERIFY = "DD_CONSUL_VERIFY"
ENV_HOST_TAGS        = "DD_HOST_TAGS"
ENV_HOST_LABELS      = "DD_HOST_LABELS"
ENV_CONTAINER_LABELS = "DD_CONTAINER_LABELS"
ENV_IS_KUBERNETES    = "DD_KUBERNETES"
ENV_IS_DEBIAN_IMAGE  = "DD_IS_DEBIAN_IMAGE"

# METADATA API
TIMEOUT = 15
METADATA_API_URL = "http://%s/latest" % (os.getenv('DD_METADATA_HOSTNAME','rancher-metadata'))

# CONFIGURATION FILES
DD_AGENT_CONFIG_DEBIAN = "/etc/dd-agent/datadog.conf"
DD_DOCKER_CONFIG_DEBIAN = "/etc/dd-agent/conf.d/docker_daemon.yaml"
DD_AGENT_CONFIG_ALPINE = "/opt/datadog-agent/agent/datadog.conf"
DD_DOCKER_CONFIG_ALPINE = "/opt/datadog-agent/agent/conf.d/docker_daemon.yaml"

def get_metadata(path, timeout=0):
	timeout_at = time.time()+timeout
	while True:
		try:
			response = requests.get(url="%s%s" % (METADATA_API_URL, path), 
									timeout=(5.0, 5.0),
									headers = {"Accept": "application/json"})
			response.raise_for_status()
		except requests.exceptions.RequestException as e:
			if time.time() > timeout_at:
				raise RuntimeError("Failed to query Rancher Metadata (%s): %s" % (path, str(e)))
			time.sleep(1.0)
			continue
		try:
			json_obj = response.json()
		except ValueError, e:
			if time.time() > timeout_at:
				raise RuntimeError("Could not decode response from Rancher Metadata API (%s) %s" % (path, str(e)))
			time.sleep(1.0)
			continue
		break
	return json_obj

def rewrite_config(filename, replacements):
	with open(filename, "r") as f:
		lines = f.readlines()
	tmp_file = filename + ".tmp"
	with open(tmp_file, "w") as temp:
		for line in lines:
			for match, replace in replacements.iteritems():
				line, i = re.subn(match, replace, line)
				if i > 0:
					break
			temp.write(line)
		temp.close()
	os.rename(tmp_file, filename)

def append_config(filename, append_str):
	with open(filename, "a") as f:
		f.write(append_str)

def main():
	tags = list()
	host_labels = list()
	container_labels = list()
	host_tags = dict()
	replace_conf_agent = dict()
	replace_conf_docker = dict()
	append_agent_conf = ''
	agent_conf_path = ''
	docker_conf_Path = ''

	if os.getenv(ENV_IS_DEBIAN_IMAGE, 'false') == 'true':
		agent_conf_path = DD_AGENT_CONFIG_DEBIAN
		docker_conf_Path = DD_DOCKER_CONFIG_DEBIAN
	else:
		agent_conf_path = DD_AGENT_CONFIG_ALPINE
		docker_conf_Path = DD_DOCKER_CONFIG_ALPINE

	if os.getenv(ENV_HOST_TAGS):
		tags = [item.strip() for item in os.getenv(ENV_HOST_TAGS, '').split(',')]
		host_tags = dict([tag.split(':') if ':' in tag else [tag, None] for tag in tags])

	if os.getenv(ENV_HOST_LABELS):
		host_labels = [item.strip() for item in os.getenv(ENV_HOST_LABELS,'').split(',')]
	
	print "Querying Rancher Metadata API"
	host = get_metadata('/self/host', TIMEOUT)
	hostname = host.get('name', '')
	for key, value in host.get('labels', {}).iteritems():
		if key in host_labels:
			host_tags[key] = value

	# TODO: set to environment instead of rewriting datadog.conf. Depends on DD Alpine image bug fix.
	if host_tags:
		host_tags_str = ", ".join(['%s:%s' % (key, value) if value is not None else key for (key, value) in host_tags.items()])
		replace_conf_agent["# ?tags:.*$"] = "tags: %s" % host_tags_str

	if hostname:
		replace_conf_agent["# ?hostname:.*$"] = "hostname: %s" % hostname

	print "Hostname: %s" % hostname
	print "Exporting host labels as host tags:"
	for key in host_tags:
		print ("- %s=%s" % (key, host_tags[key]) if host_tags[key] is not None else "- %s" % key)

	# Don't export service labels when running in Kubernetes
	if not os.getenv(ENV_IS_KUBERNETES):
		if os.getenv(ENV_CONTAINER_LABELS):
			env_container_labels = set([item.strip() for item in os.getenv(ENV_CONTAINER_LABELS,'').split(',')])
			container_labels = list(env_container_labels)
			replace_conf_docker["# ?collect_labels_as_tags:.*$"] = "collect_labels_as_tags: %s" % container_labels
			print "Exporting container labels as tags:"
			for item in container_labels:
				print "- %s" % item

	rewrite_config(DD_AGENT_CONFIG, replace_conf_agent)
	rewrite_config(DD_DOCKER_CONFIG, replace_conf_docker)

	# Service Discovery
	sd_enabled = os.getenv(ENV_SD_ENABLED, 'false').lower()
	sd_config_backend = os.getenv(ENV_SD_BACKEND_TYPE, 'none').lower()
	sd_config_backend_host = os.getenv(ENV_SD_BACKEND_HOST)
	sd_config_backend_port = os.getenv(ENV_SD_BACKEND_PORT)
	sd_config_template_dir = os.getenv(ENV_SD_TEMPLATE_DIR)
	if sd_enabled == 'true':
		print "Enabling Service Discovery"
		append_agent_conf = ''
		append_agent_conf += "service_discovery_backend: docker\n"
		if sd_config_backend != 'none':
			append_agent_conf += "sd_config_backend: %s\n" % sd_config_backend
			if not sd_config_backend_host:
				sys.exit('Environment variable %s is not set!') % ENV_SD_BACKEND_HOST
			if not sd_config_backend_port:
				sys.exit('Environment variable %s is not set!') % ENV_SD_BACKEND_PORT
			append_agent_conf += "sd_backend_host: %s\n" % sd_config_backend_host
			append_agent_conf += "sd_backend_port: %s\n" % sd_config_backend_port
		if sd_config_backend == 'consul':
			if os.getenv(ENV_SD_CONSUL_TOKEN):
				append_agent_conf += "consul_token: %s\n" % os.getenv(ENV_SD_CONSUL_TOKEN)
			if os.getenv(ENV_SD_CONSUL_SCHEME):
				append_agent_conf += "consul_scheme: %s\n" % os.getenv(ENV_SD_CONSUL_SCHEME)
			if os.getenv(ENV_SD_CONSUL_VERIFY):
				append_agent_conf += "consul_verify: %s\n" % os.getenv(ENV_SD_CONSUL_VERIFY)

		if sd_config_template_dir:
			append_agent_conf += "sd_template_dir: %s\n" % sd_config_template_dir

	# Write extra agent conf
	if append_agent_conf:
		append_config(DD_AGENT_CONFIG, append_agent_conf)

	# Exec docker-dd-agent image entrypoint
	os.execv("/entrypoint.sh", sys.argv)

if __name__ == "__main__":
	main()
