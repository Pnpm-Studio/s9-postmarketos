# S9 IRQ affinity

`irq-affinity.start` belongs in `/etc/local.d/` (executable, OpenRC `local`
in the default runlevel). It keeps the Wi-Fi and MAX77705 I2C controller
interrupts on the little cluster, CPUs 0–3. Select by controller name, not IRQ number.

The vendor I2C driver normally forces each interrupt onto the CPU starting the
transfer, overwriting userspace affinity. `07-i2c-preserve-irq-affinity.patch`
removes that override. It applies to Exynos9810-LTS
`android_kernel_samsung_universal9810` revision
`5eaa43c40667ef407f826ca2bab9552568327c23`. It changes every interrupt-mode
Exynos5 I2C controller; only the MAX77705 controller is pinned by this script.

Build workspace: `~/projects/oldphones/s9`, package
`pmaports/device/archived/linux-samsung-starlte` (patch listed in `source` and
SHA-512 checksums, package release 1). Use
`pmbootstrap -c pmbootstrap-generic.cfg build --lax --force linux-samsung-starlte`.
The native chroot also needs `binutils-aarch64` for the vendor kernel's external
assembler; install with `pmbootstrap -c pmbootstrap-generic.cfg chroot -- apk add binutils-aarch64`.

Before deploying, preserve BOOT and the current `/boot` files. The initial
recovery set is `~/Backups/s9-irq162-2026-10-15/` on the host, including BOOT,
RECOVERY and the original kernel APK. Do not overwrite RECOVERY. If the new
kernel does not boot, restore `BOOT.img` to BOOT using TWRP or Download Mode
and Heimdall; restoring requires physical access.

Acceptance after reboot: identify the new kernel build, verify IRQ162 affinity
stays `0-3` while interrupt counts advance and big cores hotplug, check no fresh
IRQ162 affinity warnings or I2C transfer timeouts, and verify charging/battery
telemetry, display, USB SSH and Wi-Fi still work.

## First hardware test (2026-10-15)

The `r1` package built with Alpine clang 23.1.3. The test boot image preserves
the known-working ramdisk, DT and boot header/arguments byte-for-byte; only the
kernel payload differs. Original-image unpack/repack reproduced its SHA-256.
The kernel package was installed with `apk add --no-scripts` because its normal
initramfs hooks were deliberately replaced by this validated manual repack.
`/boot/boot.img` was written to BOOT and its exact payload readback matched
SHA-256 `47b5d818dc017d481f35abc21334be18b51bc0c6a721b3cf4a6fe483756862c6`.

After an SSH reboot, `/proc/version` identifies `#2-postmarketOS`, and boot ID
changed to `2ef33316-58dc-4dc1-968f-55000603808b`. USB SSH, Wi-Fi SSH, dashboard
and display service returned; MAX77705 telemetry reports Charging and Good.
IRQ162 reads `0-3`, with zero unhandled interrupts. A timed hotplug/traffic
verification capture is in `~/projects/oldphones/s9/logs/irq162-check-20261015.json`.

The 50-second capture observed 1,993 IRQ162 interrupts, affinity `0-3` in every
sample, 11 big-core shutdown log events, zero IRQ162 affinity warnings and zero
unhandled interrupts. Boot-time `14370000.hsi2c` / `mfc_get_chip_id` error lines
also exist in the unpatched `s9/logs/boot2`, `boot3` and `boot4` captures; they
are a separate wireless-charger probe issue. `ret_error 0` MAX77705 messages
are diagnostic strings, not failed transfers. No new IRQ162 failure was observed.

## Boot-warning follow-up

`08-devfreq-start-worker.patch` starts each vendor simpleinteractive worker
after binding, so it reaches its interruptible wait instead of remaining in
the kthread-create D state. A stop check prevents a shutdown wake from
performing a final frequency update. Test its actual patched C worker with
`python3 power/test_devfreq_worker.py /path/to/governor_simpleinteractive.c`.

`wifi/09-dhd-boot-runtime-policy.patch` applies the existing `idletime 0`
policy from driver startup, and avoids reporting a successful VHT feature
configuration (`ret == 0`) as an error. This keeps PCIe runtime suspend off;
it does not disable 802.11 power saving or change system-suspend paths.

The follow-up package is release 2 (`#3-postmarketOS`). Its isolated build
configuration is `~/projects/oldphones/s9/pmbootstrap-boot-errors.cfg`, with
work directory `~/projects/oldphones/s9/work-boot-errors`. No new rootfs is
installed; only the kernel package and preserved-components boot image.

R2 acceptance: rebooted to `#3-postmarketOS`; at 301 seconds all nine workers
were interruptible and the targeted warnings were absent. The 50-second IRQ
capture observed 1,283 interrupts, affinity always `0-3`, zero unhandled IRQs.
Evidence: `s9/logs/boot-errors-after-r2.log` and
`s9/logs/irq162-r2-check-20261015.json` under oldphones. USB and Wi-Fi SSH work.
The pre-existing wireless-charger probe NACK remains separate.

## Wireless receiver detection

`10-mfc-detect-transition.patch` samples the pad-detect GPIO before querying
chip ID and returns when the state has not changed. The original worker made
an unnecessary I2C read on an unchanged no-pad startup (`w(0 to 0)`), causing
an ENXIO/NACK while no receiver power was available. Actual transition handling,
including the existing MST guards, is retained. The host harness compiles the
actual patched worker gate/epilogue with stubs; it does not exercise charging
register programming. Run `python3 power/test_mfc_detect.py /path/to/mfc_charger.c`
against the original pinned source.

Wireless charging is enabled by default and the owner’s Qi pad was detected:
wireless online=1, battery Charging, RX voltage about 4.4 V. USB was connected
simultaneously, so this is not a measured pad-only charge-rate result. The
Battery & power toggle uses `battery/wc_control`, which controls WPC_EN;
`wc_enable` alone only updates the battery monitor flag. Saved preferences in
`/etc/s9/wireless` are restored by `wireless-charging.start`.

Separate known defect: `mfc_get_chip_id()` ignores a failed read and can classify
an uninitialized byte. Correcting that helper requires error handling in all
firmware update/verification callers; the detect-gate patch leaves those paths
unchanged. Do not interpret an “IDT CHIP” line after an I2C error as a valid ID.

The old Clang cross-native kernel also needs the native `binutils-aarch64`
package. pmbootstrap's strict build zaps that manual native tool; listing it as
a normal kernel makedependency is rejected by target-architecture resolution.
Reproduce with the isolated config, then keep that native buildroot:

```sh
pmbootstrap -c ~/projects/oldphones/s9/pmbootstrap-boot-errors.cfg chroot -- apk add binutils-aarch64
pmbootstrap -c ~/projects/oldphones/s9/pmbootstrap-boot-errors.cfg build linux-samsung-starlte --force --lax
```

The config uses 12 build jobs (all 12 available CPUs); ccache is enabled.

## Final session checkpoint

R4 includes patch11 (`wait_event_interruptible` for the hotplug governor) and is
running as `#5-postmarketOS`. R4 boot payload SHA256
`e276ec5ae43f0bc74ce2e536d4bbead88e15543da8ff035173d442ea0ea75b2a`;
readback matched. Only the kernel changed; preserved ramdisk, DT and arguments.

## Store hold (R5, `#6-postmarketOS`)

`12-store-hold.patch` replaces Samsung's store-mode policy (cap 70%): at the
cap it uses CHARGING_OFF with the input buck left on, so external power carries
the load and the battery idles (~0 mA measured). The old ">70% → BUCK_OFF"
drain is removed for every cable; hiccup/undefined-range BUCK_OFF is kept, and
the cap and recharge act only while health is GOOD. Top-up at <=68% (was 60).
The battery supplies current only when load exceeds the input limit (PC USB
475 mA). Check: `python3 power/test_store_hold.py <kernel-src-root>`.
R5 boot SHA256 `2e941045103ffb37967208bd8fba9b9cff611c95c88a41c7843c68b407ba5c2e`;
rollback image `~/Backups/s9-store-hold-2026-10-15/BOOT-r4-readback.img`.
The earlier `power/wip/` attempt is superseded.

## ACPM IPC recheck (R6, `#7-postmarketOS`)

`13-acpm-ipc-recheck.patch` rechecks the ACPM reply before reporting
`acpm_ipc timeout`. On R5 a boot logged 42 such retries. On R6, a llama-server
run (MiniCPM5 2B Q6_K) logged 0. Check: `python3 power/test_acpm_recheck.py <kernel-src-root>`.
R6 boot SHA256 `025bb8a5ecfee9bee2e40b58026a8484d1f0098ed020cd01f5d46691fb9b9403`;
readback matched. Rollback image `~/Backups/s9-acpm-r6-2026-10-15/BOOT-r5-readback.img`.

## Quad cap knob (R7, `#8-postmarketOS`)

`14-hpgov-quad-freq.patch` adds `/sys/devices/system/cpu/cpuhotplug/governor/quad_freq`
(kHz, DT `quad_freq` 1794000 .. single max 2704000; boot default = DT, so no change unless
written). It raises the validator table before the cap and never lowers it, so
`exynos_hpgov_validate_*()` cannot BUG; also fixes the param store leaving
`attrib_lock` held on bad input. Check: `python3 power/test_hpgov_quad_freq.py <kernel-src-root>`.
First test (2026-10-15, no cooling, PC USB 475 mA, 31% battery): 4-core llama load
already draws ~1.2 A from the battery at 1.79 GHz, BIG reaches ~79 °C and power_allocator
throttles to 1.69-1.79 GHz even with cap 2314000; battery sagged to 3.495 V and the test
guard stopped it. Higher caps need a wall charger and cooling.
R7 boot SHA256 `132b4ebf64418d4a1234efd4aa33a0d28f4cd4faef2ed82706127a4c503adbf5`;
rollback image `~/Backups/s9-quadcap-r7-2026-10-15/BOOT-r6-readback.img`.

**Overclock (opt-in):** CPU & GPU limits page → *Overclock* toggle, behind two warnings (strong charger + cooling, then accepting the fire risk). On = quad_freq 2314000, BIG `sustainable_power` 3500, `trip_point_2_temp` 88000 (off: 1794000 / 2000 / 83000), saved in `/etc/s9/overclock` (0 = off, else the 4-core cap in kHz; `1` = 2314000; default off). While on, the page's *4-core cap* row steps quad_freq from 1.79 up to 2.70 GHz and saves it there and re-applied at boot by `overclock.start`. The *Throttle at* row sets `trip_point_2_temp` from 83 to 100 °C (saved in `/etc/s9/overclock-trip`, reset to 88 °C each time overclock is turned on) and raises thermal-guard's SoC shutdown limit to at least 5 °C above it (in `/etc/local.d/`, only if `thermal_zone0` is `BIG`). Measured on a 3 A USB-C port, no fan: llama prefill 8.17 / gen 5.35 t/s (+13 %), clocks mostly 1.92–2.11 GHz, peak 86 °C, battery −0.8 A at worst.

## USB input current

A PC port that only advertises default Type-C current gets the stock 475 mA, which is less than the phone draws under
llama load (the battery drained at about 1.2 A). `usb-input.start` (in `/etc/local.d/`) raises that case to 900 mA, the USB 3 port rating,
through `batt_tune_input_charge_current`. Measured on a PC port: input 475 → 887 mA, battery −1168 → +545 mA, VBUS 4.57 V.
A USB-C port that advertises 3 A already gets 2100 mA from the kernel (`sec_bat_set_rp_current`); max77705 AICL
settled at 1300 mA there. Each cable attach reloads the stock table, so wall chargers keep their 1.8 A.
