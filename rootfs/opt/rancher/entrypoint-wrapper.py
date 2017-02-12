#!/opt/datadog-agent/embedded/bin/python
'''
	Rancher sidekick entrypoint wrapper for datadog/docker-dd-agent
	Used in Datadog Rancher Catalog stack for Cattle and Kubernetes environments

	Configuration passed via environment variables:
	DD_SERVICE_DISCOVERY - whether to enable service discovery (true|false)
	DD_SD_CONFIG_BACKEND - configuration backend for service discovery (none|etcd|consul)
	DD_CONSUL_TOKEN - Consul ACL token granting read access to the configuration template path
	DD_CONSUL_SCHEME - Scheme used to connect to Consul store (http|https)
	DD_CONSUL_VERIFY - Whether to verify the SSL certificate for HTTPS requests (true|false)
	DD_HOST_LABELS - comma seperated list of host labels to export as Datadog host tags
	DD_CONTAINER_LABELS - comma seperated list of container labels to export as Datadog metric tags
	DD_KUBERNETES - if set, skips export of container labels as tags
	DD_METADATA_HOSTNAME - hostname used to query Rancher's metadata service, default: rancher-metadata
	----
	Copyright (c) 2016 Rancher Labs, Inc.
	Licensed under the Apache License, Version 2.0 (see LICENSE)
	
'''

import requests
import time
import re
import json
import os
import sys

TIMEOUT = 15
METADATA_API_URL = "http://%s/latest" % (os.environ.get('DD_METADATA_HOSTNAME','rancher-metadata'))
DD_AGENT_CONFIG = "/etc/dd-agent/datadog.conf"
DD_DOCKER_CONFIG = "/etc/dd-agent/conf.d/docker_daemon.yaml"

DEFAULT_CONTAINER_LABELS = set([
	"io.rancher.stack.name",
	"io.rancher.stack_service.name",
])

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
	dd_env_config = dict()

	'''
	Datadog Agent config environment variables:
	DD_HOSTNAME
	TAGS
	DOGSTATSD_ONLY
	SD_BACKEND
	SD_CONFIG_BACKEND
	'''

	if os.environ.get('TAGS', ''):
		tags = [item.strip() for item in os.environ.get('TAGS', '').split(',')]
		host_tags = dict([tag.split(':') if ':' in tag else [tag, None] for tag in tags])

	if os.environ.get('DD_HOST_LABELS',''):
		host_labels = [item.strip() for item in os.environ.get('DD_HOST_LABELS','').split(',')]
	
	print "Querying Rancher Metadata API"
	host = get_metadata('/self/host', TIMEOUT)
	hostname = host.get('name', '')
	for key, value in host.get('labels', {}).iteritems():
		if key in host_labels:
			host_tags[key] = value

	# TODO: set to environment instead of rewriting datadog.conf. Depends on DD Alpine image bug fix.
	if host_tags:
		host_tags_str = ", ".join(['%s:%s' % (key, value) if value is not None else key for (key, value) in host_tags.items()])
		replace_conf_agent["# tags:.*$"] = "tags: %s" % host_tags_str

	if hostname:
		replace_conf_agent["# hostname:.*$"] = "hostname: %s" % hostname

	print "Hostname: %s" % hostname
	print "Exporting host labels as host tags:"
	for key in host_tags:
		print ("- %s=%s" % (key, host_tags[key]) if host_tags[key] is not None else "- %s" % key)

	# Don't export service labels in Kubernetes environments
	if not "DD_KUBERNETES" in os.environ:
		if os.environ.get('DD_CONTAINER_LABELS',''):
			env_container_labels = set([item.strip() for item in os.environ.get('DD_CONTAINER_LABELS','').split(',')])
		else:
			env_container_labels = set()
		container_labels = list(env_container_labels | DEFAULT_CONTAINER_LABELS)
		replace_conf_docker["# collect_labels_as_tags:.*$"] = "collect_labels_as_tags: %s" % container_labels
		print "Exporting container labels as metric tags:"
		for item in container_labels:
			print "- %s" % item

	rewrite_config(DD_AGENT_CONFIG, replace_conf_agent)
	rewrite_config(DD_DOCKER_CONFIG, replace_conf_docker)

	# Service Discovery
	sd_enabled = os.getenv('DD_SERVICE_DISCOVERY', 'false').lower()
	sd_backend = os.getenv('DD_SD_CONFIG_BACKEND', 'none').lower()
	if sd_enabled == 'true':
		dd_env_config['SD_BACKEND'] = 'docker'
		if sd_backend != 'none':
			dd_env_config['SD_CONFIG_BACKEND'] = sd_backend
		if sd_backend == 'consul':
			append_agent_conf = ''
			if os.getenv('DD_CONSUL_TOKEN'):
				append_agent_conf += "consul_token: %s\n" % os.getenv('DD_CONSUL_TOKEN')
			if os.getenv('DD_CONSUL_SCHEME'):
				append_agent_conf += "consul_scheme: %s\n" % os.getenv('DD_CONSUL_SCHEME')
			if os.getenv('DD_CONSUL_VERIFY'):
				append_agent_conf += "consul_verify: %s\n" % os.getenv('DD_CONSUL_VERIFY')
			if append_agent_conf:
				append_config(DD_AGENT_CONFIG, append_agent_conf)

	# Export dd-agent config
	for k, v in dd_env_config.iteritems():
		os.environ[k] = v

	# Exec docker-dd-agent image entrypoint
	os.execv("/entrypoint.sh", sys.argv)

if __name__ == "__main__":
	main()
