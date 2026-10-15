# Docker on the S9 (stock 4.9 kernel)

Full Docker: overlay2 on /srv, bridge network, published ports.

- `rc_cgroup_mode="legacy"` in `/etc/rc.conf`: 4.9 has no cgroup-v2 BPF device control (crun: `bpf create: Invalid argument`).
- runtime `crun`: runc 1.5 panics in libpathrs on 4.9 (`/proc/thread-self` check).
- `schedtune-off` service: Android schedtune cgroup gives ENOMEM.
- `conf.d-docker`: dockerd gets iptables-legacy via PATH. nft iptables can't load `addrtype` on 4.9, and the firewall uses legacy tables anyway.
- `/proc/config.gz` on this kernel is stale: it says no BRIDGE/OVERLAY_FS, both work.
- Published ports (`-p`) bypass the INPUT firewall (normal Docker behavior).

Install: `apk add docker docker-openrc crun`; `daemon.json` -> `/etc/docker/`; `schedtune-off` -> `/etc/init.d/`; `conf.d-docker` -> `/etc/conf.d/docker`; `mkdir /usr/local/libexec/iptables-legacy` with symlinks `iptables{,-save,-restore}` and `ip6tables{,-save,-restore}` to the `/sbin/*-legacy*` binaries; `rc-update add schedtune-off default; rc-update add docker default`.
