# Kernel: linux-samsung-starlte 4.9.299-r10

pmaports package `device/archived/linux-samsung-starlte` as built for the release.
Source: [Exynos9810-LTS/android_kernel_samsung_universal9810](https://github.com/Exynos9810-LTS/android_kernel_samsung_universal9810) @ `5eaa43c40667ef407f826ca2bab9552568327c23`.

- `01`-`06`: from upstream pmaports (decon display fixes, Wi-Fi firmware path, relocation build fix).
- `07`-`15`: ours. `07`, `08`, `10`-`14` are documented in [power/README.md](../power/README.md), `09` in `wifi/`; the files here are symlinks to them. `15` gives fbcon working decon blit ops (tty1 console) and drops a per-frame `setcolreg` printk.

Use: `cp -rL kernel/. <pmaports>/device/archived/linux-samsung-starlte/` (`-L` resolves the symlinks), then `pmbootstrap build linux-samsung-starlte`.
