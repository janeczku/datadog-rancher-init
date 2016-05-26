#!/opt/datadog-agent/embedded/bin/python
'''
	Rancher sidekick entrypoint wrapper for datadog/docker-dd-agent
	Used in Datadog Rancher Catalog stack for Cattle and Kubernetes environments

	Configuration passed via environment variables:
	DOGSTATSD_ONLY - standalone DogStatsD (true|false)
	HOST_LABELS - comma seperated list of host labels to map to Datadog tags
	CONTAINER_LABELS - comma seperated list of container labels to map to Datadog tags
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
METADATA_API_URL = "http://rancher-metadata/latest"
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
		break
	try:
		json_obj = response.json()
	except ValueError, e:
		raise RuntimeError("Could not decode response from Rancher Metadata API (%s) %s" % (path, str(e)))
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

def main():
	env_dogstatsd_only = os.environ.get('DOGSTATSD_ONLY','')
	host_labels = list()
	container_labels = list()
	host_tags = dict()
	replace_conf_agent = dict()
	replace_conf_docker = dict()

	if len(os.environ.get('HOST_LABELS','')) > 0:
		host_labels = [item.strip() for item in os.environ.get('HOST_LABELS','').split(',')]
	
	print "Querying Rancher Metadata API"

	host = get_metadata('/self/host', TIMEOUT)
	hostname = host.get('name', '')
	for key, value in host.get('labels', {}).iteritems():
		if key in host_labels:
			host_tags[key] = value

	if host_tags:
		host_tags_str = ", ".join(['%s:%s' % (key, value) for (key, value) in host_tags.items()])
		replace_conf_agent["#tags:.*$"] = "tags: %s" % host_tags_str

	if hostname:
		replace_conf_agent["#hostname:.*$"] = "hostname: %s" % hostname

	print "Hostname: %s" % hostname
	print "Host labels as tags:"
	for key in host_tags:
		print "- %s=%s" % (key, host_tags[key])

	# We only map container labels in Rancher Cattle environment.
	if not "KUBE_SIDEKICK" in os.environ:
		if len(os.environ.get('CONTAINER_LABELS','')) > 0:
			env_container_labels = set([item.strip() for item in os.environ.get('CONTAINER_LABELS','').split(',')])
		else:
			env_container_labels = set()
		container_labels = list(env_container_labels | DEFAULT_CONTAINER_LABELS)
		replace_conf_docker["# collect_labels_as_tags:.*$"] = "collect_labels_as_tags: %s" % container_labels
		print "Container labels as tags:"
		for item in container_labels:
			print "- %s" % item

	rewrite_config(DD_AGENT_CONFIG, replace_conf_agent)
	rewrite_config(DD_DOCKER_CONFIG, replace_conf_docker)

	# Unset DOGSTATSD_ONLY environment variable
	if env_dogstatsd_only == 'false':
		del os.environ['DOGSTATSD_ONLY']

	# Exec docker-dd-agent image entrypoint
	os.execv("/entrypoint.sh", sys.argv)

if __name__ == "__main__":
	main()