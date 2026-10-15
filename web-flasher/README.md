# S9 web flasher

Browser installer for the Samsung Galaxy S9 **SM-G960F (Exynos, samsung-starlte)** only; not the Snapdragon
SM-G9600. Static page over WebUSB; files stay in the browser and stream to the phone over USB. If the images and the TWRP
.img sit next to `index.html` (same origin), the "Download from this site" buttons fetch and select them;
otherwise use the file pickers. Either way each file is checked against the pinned size and SHA-256 before any write.
**Experimental: not hardware-tested end to end.** Use desktop Chrome or Edge on `localhost` or HTTPS.

1. **Install TWRP** (skip if you have it). Download Mode, Odin protocol via
   [`@lineageos-infra/libmjolnir`](https://github.com/lineageos-infra/libmjolnir) (MIT). Writes only `RECOVERY`
   after the pinned TWRP 3.7.0 SHA-256 and the phone's PIT check. Never reboots: boot straight into TWRP
   (Vol Down + Power until black, then Vol Up + Bixby + Power) or stock restores its recovery.
2. **Flash the postmarketOS image** from TWRP over ADB
   ([`@yume-chan/adb`](https://github.com/yume-chan/ya-webadb), MIT). Checks `ro.product.device == starlte`, TWRP,
   by-name block devices, sizes and mounts; streams each image through `dd of=<by-name>` (ADB shell v2 only);
   re-reads and SHA-256-checks every written range on the phone. Order SYSTEM, VENDOR, BOOT. Optional USERDATA
   format (ext4, label `s9-srv`, unmounts /data and /sdcard first; off by default) and reboot. Any mismatch stops.

## Build and run

```sh
cd web-flasher
npm ci --ignore-scripts
npm run check && npm test && npm run build
cp <W>/out/{boot.img,samsung-starlte-root.img,samsung-starlte-boot.img} <twrp.img> dist/   # optional: enables the download buttons
python3 -m http.server 8085 --bind 127.0.0.1 --directory dist   # http://localhost:8085
```

## Pins

`site/s9-manifest.js` is the single pin block (names, partitions, sizes, SHA-256). Section 2 refuses to run
while it holds placeholders. After a new image build:
`node scripts/fill-s9-manifest.mjs <pkg-out-dir> <release>`, then compare with the build's `SHA256SUMS`.
Image names: `boot.img` (BOOT), `samsung-starlte-root.img` (SYSTEM), `samsung-starlte-boot.img` (VENDOR).

## Layout

`site/s9.js` logic (mock-tested in `test/s9.test.js`), `site/s9-usb.js` WebUSB glue, `site/s9-app.js` UI wiring,
`site/hash.js` streaming SHA-256, `dist/THIRD-PARTY-NOTICES.txt` licences of the bundled libraries.
Never put stock firmware, credentials or personalised images here. Do not run host `adb` while Chrome holds the phone.
