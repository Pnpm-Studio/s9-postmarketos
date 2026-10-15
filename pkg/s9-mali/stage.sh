#!/bin/sh
# Assemble s9-mali from the stock Android 10 blobs (G960FXXUHFVG4, extracted to <workdir>/android-blobs).
# Only the libraries libGLES_mali.so and the bionic linker need are copied (~46 MB of the 1.3 GB system+vendor).
# Usage: sh pkg/s9-mali/stage.sh [pmbootstrap-workdir]   (default ~/projects/oldphones/s9)
set -eu
P=$(cd "$(dirname "$0")" && pwd)
W=${1:-$HOME/projects/oldphones/s9}
B=$W/android-blobs
A=$W/pmaports/main/s9-mali
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
D=$T/root
M=$D/usr/lib/s9-mali/root
LINKER=system/apex/com.android.runtime.release/bin/linker64

mkdir -p "$M"
files=$(python3 "$P/closure.py" "$B" vendor/lib64/egl/libGLES_mali.so $LINKER)
(cd "$B" && cp -a --parents -L $files $LINKER "$M/")
cd "$M"
mkdir -p system/bin apex dev proc sys tmp models opt/vk opt/bin
ln -s /apex/com.android.runtime/bin/linker64 system/bin/linker64
ln -s ../system/apex/com.android.runtime.release apex/com.android.runtime
ln -s /vendor/lib64/egl/libGLES_mali.so opt/vk/libvulkan.so
install -m755 "$W/gpu/vkprobe" opt/bin/vkprobe
install -Dm755 "$P/mali-run" "$D/usr/bin/mali-run"
install -Dm755 "$P/s9-mali.initd" "$D/etc/init.d/s9-mali"

mkdir -p "$A"
tar -C "$T" --owner=0 --group=0 --numeric-owner -czf "$A/s9-mali-root.tar.gz" root
cp "$P/APKBUILD" "$P/s9-mali.post-install" "$A/"
cd "$W" && pmbootstrap -c pmbootstrap.cfg checksum s9-mali
