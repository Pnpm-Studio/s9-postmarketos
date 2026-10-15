#!/bin/sh
# Run from the PC: copies dashboard/ to the phone, installs it to /opt/s9-dashboard + an OpenRC service, (re)starts it.
# Usage: sh deploy.sh [ssh-host]   default host s9 (needs sudo on the phone; asks for its password)
set -eu
R=$(cd "$(dirname "$0")" && pwd)
H=${1:-s9}
T=$(ssh "$H" mktemp -d)
scp -q "$R"/dashboard/*.py "$R"/dashboard/index.html "$R"/dashboard/s9-dashboard.initd "$H:$T/"
ssh -t "$H" "sudo sh -ec '
    install -d -o \$(id -un 1000) -g \$(id -gn 1000) /opt/s9-dashboard
    install -m644 -o \$(id -un 1000) -g \$(id -gn 1000) $T/*.py $T/index.html /opt/s9-dashboard/
    install -m755 $T/s9-dashboard.initd /etc/init.d/s9-dashboard
    rc-update add s9-dashboard default
    rc-service s9-dashboard restart
    rm -rf $T'"
