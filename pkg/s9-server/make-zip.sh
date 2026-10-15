#!/bin/sh
# Pack the pmbootstrap --split output into out/: raw images, sha256, and TWRP zips.
# Usage: sh pkg/s9-server/make-zip.sh [pmbootstrap-workdir] [outdir]   (PMB_WORK=<dir> if the cfg's work= is not <workdir>/work)
# DEV=samsung-star2lte packs the S9+ build.
set -eu
P=$(cd "$(dirname "$0")" && pwd)
W=${1:-$HOME/projects/oldphones/s9}
O=${2:-$W/out}
PW=${PMB_WORK:-$W/work}
DEV=${DEV:-samsung-starlte}
CH=$PW/chroot_native/home/pmos/rootfs
BOOTIMG=$PW/chroot_rootfs_$DEV/boot/boot.img
mkdir -p "$O"
cp "$BOOTIMG" "$O/boot.img"
sudo cat "$CH/$DEV-root.img" > "$O/$DEV-root.img"
sudo cat "$CH/$DEV-boot.img" > "$O/$DEV-boot.img"
# must fit the real partitions (BOOT, SYSTEM, VENDOR)
[ "$(stat -c %s "$O/boot.img")" -le 57671680 ] && [ "$(stat -c %s "$O/$DEV-root.img")" -le 4613734400 ] && [ "$(stat -c %s "$O/$DEV-boot.img")" -le 681574400 ] || { echo "image too big for its partition" >&2; exit 1; }
(cd "$O" && sha256sum boot.img $DEV-root.img $DEV-boot.img > SHA256SUMS)
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
for i in boot.img $DEV-root.img $DEV-boot.img; do gzip -9 -c "$O/$i" > "$T/$i.gz"; done
sz() { stat -c %s "$O/$1"; }; sh_() { sha256sum "$O/$1" | cut -d' ' -f1; }
F="flash boot.img.gz $(sz boot.img) $(sh_ boot.img) \"\$BOOT\"
flash $DEV-root.img.gz $(sz $DEV-root.img) $(sh_ $DEV-root.img) \"\$SYSTEM\"
flash $DEV-boot.img.gz $(sz $DEV-boot.img) $(sh_ $DEV-boot.img) \"\$VENDOR\""
for srv in 0 1; do
	D=$T/z$srv; mkdir -p "$D/META-INF/com/google/android"
	U=$D/META-INF/com/google/android/update-binary
	awk -v f="$F" -v s=$srv -v d="${DEV#samsung-}" '{gsub(/@SRV@/,s); gsub(/@DEVICE@/,d); if ($0=="@FLASH@") print f; else print}' "$P/twrp-update-binary" > "$U"
	echo "# dummy" > "$D/META-INF/com/google/android/updater-script"
	cp "$T"/*.gz "$D/"
	n=s9-server-twrp.zip; [ $srv = 0 ] || n=s9-server-twrp-srv.zip
	rm -f "$O/$n"; python3 -I -c 'import zipfile,os,sys
z=zipfile.ZipFile(sys.argv[2],"w",zipfile.ZIP_STORED)
for r,_,fs in os.walk(sys.argv[1]):
    for f in fs:
        a=os.path.join(r,f); z.write(a,os.path.relpath(a,sys.argv[1]))' "$D" "$O/$n"
done
(cd "$O" && sha256sum *.zip >> SHA256SUMS)
ls -l "$O"
