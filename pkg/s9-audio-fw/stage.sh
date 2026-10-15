#!/bin/sh
# Assemble s9-audio-fw from the stock Android 10 blobs (G960FXXUHFVG4, extracted to <workdir>/android-blobs):
# the abox/vts DSP firmware s9-audio feeds to the kernel, plus Samsung's mixer_paths.xml.
# Usage: sh pkg/s9-audio-fw/stage.sh [pmbootstrap-workdir]   (default ~/projects/oldphones/s9)
set -eu
P=$(cd "$(dirname "$0")" && pwd)
W=${1:-$HOME/projects/oldphones/s9}
B=$W/android-blobs/vendor
A=$W/pmaports/main/s9-audio-fw
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
D=$T/root

mkdir -p "$D/lib/firmware"
for f in calliope_sram.bin calliope_dram.bin calliope_iva.bin vts.bin dsm.bin dsm_tune.bin \
	AP_AUDIO_SLSI.bin APBargeIn_AUDIO_SLSI.bin APDV_AUDIO_SLSI.bin APBiBF_AUDIO_SLSI.bin SoundBoosterParam.bin; do
	install -m644 "$B/firmware/$f" "$D/lib/firmware/$f"
done
install -Dm644 "$B/etc/mixer_paths.xml" "$D/etc/s9/mixer_paths.xml"

mkdir -p "$A"
tar -C "$T" --owner=0 --group=0 --numeric-owner -czf "$A/s9-audio-fw-root.tar.gz" root
cp "$P/APKBUILD" "$A/"
cd "$W" && pmbootstrap -c pmbootstrap.cfg checksum s9-audio-fw
