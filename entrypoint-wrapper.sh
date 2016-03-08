#!/bin/bash
#set -e

###########################################################
# Wrapper for the datadog/docker-dd-agent entrypoint script
# Expected environment variable: HOST_LABELS
###########################################################

#
# Utility funcs
#

PYTHON=/opt/datadog-agent/embedded/bin/python2

function joinStrings()
{
    local IFS="$1"
    shift
    echo "$*"
}

function get_url()
{
val=`$PYTHON -c "
import requests
r = requests.get('$1')
if r.status_code != 200:
    print ""
else:
    print r.text"`

echo "$val"
}

function get_metadata()
{
    TAGS_ARRAY=()
    HOST_LABELS=$(echo $HOST_LABELS | tr -d ' ')
    IFS=',' read -ra LABELS <<< "$HOST_LABELS"
    for i in "${LABELS[@]}"; do
        val=$(get_url "http://rancher-metadata/latest/self/host/labels/${i}")
        if [[ $val ]]; then
            keyval="$i:$val"
            TAGS_ARRAY+=("$i:$val")
        fi
    done
    TAGS=$(joinStrings , "${TAGS_ARRAY[@]}")
    HOSTNAME=$(get_url "http://rancher-metadata/latest/self/host/name")
}

#
# Wait for Metadata Service to become reachable (timeout: 20secs)
#

deadline=$((SECONDS+20))
reachable=false

while [ $SECONDS -lt $deadline ]; do
    ping -c1 rancher-metadata &> /dev/null
    if [ "$?" -eq 0 ]; then
        reachable=true
        break
    fi
echo "Connecting to Rancher Metadata service"
sleep 1
done

if [ "$reachable" = false ]; then
    echo "Could not connect to Rancher Metadata service"
    exit 1
fi

#
# Get name and labels of this host
#

get_metadata

if [[ $HOSTNAME ]]; then
    echo "Hostname: $HOSTNAME"
    sed -i -e "s/^#hostname:.*$/hostname: ${HOSTNAME}/" /etc/dd-agent/datadog.conf
fi

if [[ $TAGS ]]; then
    echo "Host labels: $TAGS"
    sed -i -e "s/^#tags:.*$/tags: ${TAGS}/" /etc/dd-agent/datadog.conf
fi

#
# Unset DOGSTATSD_ONLY environment variable if set to 'false'
#

if [[ "${DOGSTATSD_ONLY,,}" = "false" ]]; then
    unset DOGSTATSD_ONLY
fi

#
# Exec the original entrypoint
#

exec /entrypoint.sh "$@"
