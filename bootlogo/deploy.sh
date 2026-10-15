#!/bin/sh
# Run from the PC: installs the boot logo to /usr/local/lib/s9-bootlogo + an OpenRC sysinit service.
# Usage: sh bootlogo/deploy.sh [ssh-host]   default host s9 (needs sudo on the phone; asks for its password)
set -eu
R=$(cd "$(dirname "$0")" && pwd)
H=${1:-s9}
T=$(ssh "$H" mktemp -d)
scp -q "$R"/show.py "$R"/logo.raw.gz "$R"/s9-bootlogo.initd "$H:$T/"
ssh -t "$H" "sudo sh -ec '
    install -d /usr/local/lib/s9-bootlogo
    install -m644 $T/show.py $T/logo.raw.gz /usr/local/lib/s9-bootlogo/
    install -m755 $T/s9-bootlogo.initd /etc/init.d/s9-bootlogo
    rc-update add s9-bootlogo sysinit
    sync
    rm -rf $T'"
