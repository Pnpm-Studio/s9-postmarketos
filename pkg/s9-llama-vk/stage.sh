#!/bin/sh
# Stage the NDK llama.cpp build (llm/vulkan-mali-g72-r19.patch on a0e6dc7, <workdir>/gpu/vk-build) as s9-llama-vk.
# Rebuild first: cmake --build <workdir>/gpu/vk-build --target llama-bench llama-cli llama-server
# Usage: sh pkg/s9-llama-vk/stage.sh [pmbootstrap-workdir]   (default ~/projects/oldphones/s9)
set -eu
P=$(cd "$(dirname "$0")" && pwd)
W=${1:-$HOME/projects/oldphones/s9}
A=$W/pmaports/main/s9-llama-vk
STRIP=$(ls "$W"/ndk/*/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-strip | head -1)
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
O=$T/root/usr/lib/s9-mali/root/opt/bin
mkdir -p "$O"
for b in llama-bench llama-cli llama-server; do "$STRIP" -o "$O/$b" "$W/gpu/vk-build/bin/$b"; done

mkdir -p "$A"
tar -C "$T" --owner=0 --group=0 --numeric-owner -czf "$A/s9-llama-vk-root.tar.gz" root
cp "$P/APKBUILD" "$A/"
cd "$W" && pmbootstrap -c pmbootstrap.cfg checksum s9-llama-vk
