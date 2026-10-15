#!/bin/sh
# Run from the PC: installs the framebuffer UI to /usr/local/lib/s9-display + an OpenRC service, (re)starts it.
# Usage: sh display/deploy.sh [ssh-host]   default host s9 (needs sudo on the phone; asks for its password)
set -eu
R=$(cd "$(dirname "$0")" && pwd)
H=${1:-s9}
T=$(ssh "$H" mktemp -d)
scp -q "$R"/display.py "$R"/s9-display.initd "$R"/wifi-setup "$R"/wifi-ip "$R"/bt-apply "$R"/web-apply "$R"/user-apply "$R"/bluetooth.start "$R"/../wifi/wifi.start "$R"/../wifi/dhd-iovar.py "$R"/../power/wireless-charging.start "$H:$T/"
ssh -t "$H" "sudo sh -ec '
    install -d /usr/local/lib/s9-display
    install -m755 $T/display.py /usr/local/lib/s9-display/display.py
    install -m755 $T/wifi-setup /usr/local/bin/wifi-setup
    install -m755 $T/wifi-ip /usr/local/bin/wifi-ip
    install -m755 $T/dhd-iovar.py /usr/local/bin/dhd-iovar
    install -m755 $T/bt-apply /usr/local/bin/bt-apply
    install -m755 $T/web-apply /usr/local/bin/web-apply
    install -m755 $T/user-apply /usr/local/bin/user-apply
    install -m755 $T/bluetooth.start $T/wifi.start $T/wireless-charging.start /etc/local.d/
    install -m755 $T/s9-display.initd /etc/init.d/s9-display
    rc-update add s9-display default
    rc-service s9-display restart
    rm -rf $T'"
