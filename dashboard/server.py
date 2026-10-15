#!/usr/bin/env python3
"""Small Galaxy S9 status dashboard (read-only, except same-origin POSTs to kill own processes). Standard library only."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pwd
import re
import signal
import shutil
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except (OSError, UnicodeError):
        return None


def _int_value(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def zone_max(sys_root: Path, prefixes: tuple[str, ...]) -> float | None:
    """Hottest thermal zone whose type starts with one of prefixes (BIG/LITTLE/G3D/ISP/battery/ac on the S9), °C."""
    temps = []
    for z in Path(sys_root, "class/thermal").glob("thermal_zone*"):
        try:
            if z.joinpath("type").read_text().strip().startswith(prefixes):
                temps.append(int(z.joinpath("temp").read_text()) / 1000)
        except (OSError, ValueError):
            pass
    return round(max(temps), 1) if temps else None


ZONE_NAMES = {"BIG": "CPU big", "LITTLE": "CPU LITTLE", "G3D": "GPU", "ISP": "Camera ISP", "ac": "Charger", "battery": "Battery"}


def thermals(sys_root: Path) -> list[dict[str, Any]]:
    """Every thermal zone plus the USB port sensor, °C; `limit` is the first passive (throttle) trip, if any."""
    out = []
    for z in sorted(Path(sys_root, "class/thermal").glob("thermal_zone*"), key=lambda p: int(p.name[12:] or 0)):
        kind = _read_text(z / "type") or z.name
        temp = _int_value(_read_text(z / "temp"))
        if temp is None or temp == -40000:
            continue
        limit = None
        for trip in sorted(z.glob("trip_point_*_type")):
            if _read_text(trip) == "passive":
                limit = _int_value(_read_text(trip.with_name(trip.name.replace("_type", "_temp"))))
                break
        out.append({"name": ZONE_NAMES.get(kind, kind), "temp_c": round(temp / 1000, 1),
                    "limit_c": round(limit / 1000) if limit else None})
    usb = _int_value(_read_text(sys_root / "class/power_supply/battery/usb_temp"))
    if usb:  # tenths of °C; 0 = no sensor
        out.append({"name": "USB port", "temp_c": usb / 10, "limit_c": None})
    return out


def cpu_freqs_mhz(sys_root: Path) -> dict[str, int | None]:
    """Current clock of the LITTLE (policy0) and big (policy4) clusters."""
    out: dict[str, int | None] = {}
    for name, policy in (("little", "policy0"), ("big", "policy4")):
        khz = _int_value(_read_text(sys_root / "devices/system/cpu/cpufreq" / policy / "scaling_cur_freq"))
        out[name] = round(khz / 1000) if khz else None
    return out


def present_cpus(sys_root: Path) -> int | None:
    """CPUs present, online or not ("0-7" -> 8). os.cpu_count()/musl sysconf only count online ones and big cores hotplug."""
    try:
        return sum(int(r.split("-")[-1]) - int(r.split("-")[0]) + 1
                   for r in (_read_text(sys_root / "devices/system/cpu/present") or "").strip().split(","))
    except ValueError:
        return None


def loadavg(proc_root: Path) -> float | None:
    try:
        return float((_read_text(proc_root / "loadavg") or "").split()[0])  # ~13 here: D-state kernel threads, not CPU use
    except (ValueError, IndexError):
        return None


def battery_info(sys_root: Path) -> dict[str, Any]:
    supplies = sys_root / "class" / "power_supply"
    try:
        candidates = sorted(p for p in supplies.iterdir() if p.is_dir())
    except OSError:
        candidates = []
    for path in candidates:
        uevent: dict[str, str] = {}
        raw = _read_text(path / "uevent") or ""
        for line in raw.splitlines():
            key, separator, entry_value = line.partition("=")
            if separator:
                uevent[key.removeprefix("POWER_SUPPLY_")] = entry_value
        kind = _read_text(path / "type") or uevent.get("TYPE")
        if (kind or "").lower() != "battery":
            continue

        def value(key: str) -> str | None:
            return _read_text(path / key.lower()) or uevent.get(key)

        capacity = _int_value(value("CAPACITY"))
        temp = _int_value(value("TEMP"))
        voltage = _int_value(value("VOLTAGE_NOW"))
        current = _int_value(value("CURRENT_NOW"))
        present_raw = value("PRESENT")
        gauge = {
            "available": True,
            "name": uevent.get("NAME", path.name),
            "percent": smooth_pct(capacity) if capacity is not None else None,
            "status": value("STATUS"),
            "temperature_c": round(temp / 10, 1) if temp is not None else None,
            "voltage_v": round(voltage / 1_000_000, 3) if voltage is not None else None,
            "current_ma": current,  # Samsung max77705 reports mA, not uA
            "present": (present_raw not in {"0", "no", "false"}) if present_raw is not None else None,
        }
        online = [n for n in ("usb", "ac", "wireless") if (_read_text(supplies / n / "online") or "0") != "0"]
        limit = _int_value(_read_text(supplies / online[0] / "current_max")) if online else None
        return {**gauge, "plugged": bool(online), "source": online[0] if online else None,
                "input_limit_ma": limit // 1000 if limit else None, "health": value("HEALTH")}
    return {"available": False, "name": None, "percent": None, "status": None,
            "temperature_c": None, "voltage_v": None, "current_ma": None, "present": None}


from battery import smooth_pct
from gpu import gpu_info
from services import services_info


def uptime_seconds(proc_root: Path) -> float | None:
    raw = _read_text(proc_root / "uptime")
    if not raw:
        return None
    try:
        return round(float(raw.split()[0]), 1)
    except (ValueError, IndexError):
        return None


def memory_info(proc_root: Path) -> dict[str, Any]:
    raw = _read_text(proc_root / "meminfo") or ""
    values: dict[str, int] = {}
    for line in raw.splitlines():
        match = re.match(r"^(MemTotal|MemAvailable|MemFree):\s+(\d+)\s+kB", line)
        if match:
            values[match.group(1)] = int(match.group(2)) * 1024
    total = values.get("MemTotal")
    available = values.get("MemAvailable", values.get("MemFree"))
    used = max(0, total - available) if total is not None and available is not None else None
    free = values.get("MemFree")
    cached = max(0, available - free) if available is not None and free is not None else None   # reclaimable: page cache, mmap'd models
    return {"total_bytes": total, "available_bytes": available, "used_bytes": used, "free_bytes": free, "cached_bytes": cached,
            "used_percent": round(used * 100 / total, 1) if used is not None and total else None,
            "cached_percent": round(cached * 100 / total, 1) if cached is not None and total else None}


def _cpu_totals(proc_root: Path) -> tuple[int, int] | None:
    raw = _read_text(proc_root / "stat")
    if not raw:
        return None
    for line in raw.splitlines():
        fields = line.split()
        if fields and fields[0] == "cpu":
            try:
                ticks = [int(field) for field in fields[1:]]
                if len(ticks) < 4:
                    return None
                # Linux reports guest time inside user/nice too, so exclude the final
                # guest and guest_nice counters to avoid counting those ticks twice.
                total = sum(ticks[:8])
                idle = ticks[3] + (ticks[4] if len(ticks) > 4 else 0)
                return total, total - idle
            except ValueError:
                return None
    return None


def _core_totals(proc_root: Path) -> dict[int, tuple[int, int]]:
    """Per-core (total, busy) ticks from the cpuN lines of /proc/stat (offline cores are missing)."""
    cores = {}
    for line in (_read_text(proc_root / "stat") or "").splitlines():
        fields = line.split()
        if fields and fields[0][:3] == "cpu" and fields[0][3:].isdigit():
            ticks = [int(field) for field in fields[1:9]]
            cores[int(fields[0][3:])] = (sum(ticks), sum(ticks) - ticks[3] - ticks[4])
    return cores


def _disk(path: str) -> dict[str, Any]:
    try:
        usage = shutil.disk_usage(path)
        return {"path": path, "total_bytes": usage.total, "used_bytes": usage.used, "free_bytes": usage.free,
                "used_percent": round(usage.used * 100 / usage.total, 1) if usage.total else None}
    except OSError:
        return {"path": path, "total_bytes": None, "used_bytes": None, "free_bytes": None, "used_percent": None}


def storage_total(parts: list[dict[str, Any]]) -> dict[str, Any]:
    """Sum usage over all mounted partitions (/, /srv, /boot ...), one row per mountpoint."""
    seen = {r["mountpoint"]: r for r in parts if r.get("mountpoint") and r.get("total_bytes")}
    total, used, free = (sum(r[k] for r in seen.values()) for k in ("total_bytes", "used_bytes", "free_bytes"))
    return {"path": " + ".join(sorted(seen)), "total_bytes": total, "used_bytes": used, "free_bytes": free,
            "used_percent": round(used * 100 / total, 1) if total else None}


def partitions(sys_root: Path = Path("/sys"), proc_root: Path = Path("/proc")) -> list[dict[str, Any]]:
    """Every block partition with its GPT label and size, plus usage where mounted. Mounted first."""
    mounts: dict[str, tuple[str, str]] = {}
    for line in (_read_text(proc_root / "mounts") or "").splitlines():
        dev, mnt, fstype = line.split()[:3]
        if dev.startswith("/dev/"):
            mounts.setdefault(Path(dev).name, (mnt.replace("\\040", " "), fstype))
    rows = []
    for part in Path(sys_root, "class/block").glob("*"):
        if not (part / "partition").exists():
            continue
        uevent = dict(l.split("=", 1) for l in (_read_text(part / "uevent") or "").splitlines() if "=" in l)
        row: dict[str, Any] = {"name": part.name, "label": uevent.get("PARTNAME"),
                               "size_bytes": (_int_value(_read_text(part / "size")) or 0) * 512,
                               "mountpoint": None, "fstype": None}
        if part.name in mounts:
            row["mountpoint"], row["fstype"] = mounts[part.name]
            usage = _disk(row["mountpoint"])
            row.update(total_bytes=usage["total_bytes"], used_bytes=usage["used_bytes"], free_bytes=usage["free_bytes"],
                       used_percent=usage["used_percent"])
        rows.append(row)
    disk_num = lambda r: (re.sub(r"\d+$", "", r["name"]), int(re.search(r"\d*$", r["name"]).group() or 0))
    return sorted(rows, key=lambda r: (r["mountpoint"] is None, r["mountpoint"] or "", disk_num(r)))


def _process_snapshot(proc_root: Path) -> dict[int, tuple[int, int, str, int]]:
    """Return pid -> (starttime, cpu ticks, comm, RSS bytes), never command lines."""
    snapshot: dict[int, tuple[int, int, str, int]] = {}
    try:
        paths = list(proc_root.iterdir())
    except OSError:
        return snapshot
    for path in paths:
        if path.name.isdigit():
            one = _process_snapshot_pid(proc_root, int(path.name))
            if one:
                snapshot[int(path.name)] = one
    return snapshot


def _process_snapshot_pid(proc_root: Path, pid: int) -> tuple[int, int, str, int] | None:
    stat = _read_text(proc_root / str(pid) / "stat")
    if not stat:
        return None
    # comm may contain spaces and parentheses; the kernel terminates it at the final ')'.
    close = stat.rfind(")")
    if close < 0:
        return None
    try:
        fields = stat[close + 1:].split()  # starts at field 3 (state)
        cpu_ticks = int(fields[11]) + int(fields[12])  # utime + stime
        starttime = int(fields[19])
        rss_pages = int(fields[21]) if len(fields) > 21 else 0  # field 24 of /proc/PID/stat
    except (ValueError, IndexError):
        return None
    comm = stat[stat.find("(") + 1:close].strip()
    try:
        rss_bytes = rss_pages * os.sysconf("SC_PAGE_SIZE")
    except (OSError, AttributeError):
        rss_bytes = 0
    return starttime, cpu_ticks, comm, rss_bytes


def wifi_info() -> dict[str, Any]:
    """Link state and address from sysfs + ip; SSID/signal/rate from `iw dev <if> link` (apk add iw)."""
    result: dict[str, Any] = {"available": False, "connected": False, "interface": None,
                              "ssid": None, "signal_percent": None, "rate_mbps": None,
                              "ip_address": None, "quality": None, "signal_dbm": None}
    for net in sorted(Path("/sys/class/net").glob("wlan*")):
        if not (net / "wireless").exists() and not (net / "phy80211").exists():
            continue
        up = _read_text(net / "operstate") == "up"
        result.update(available=True, connected=up, interface=net.name)
        try:
            out = subprocess.run(["ip", "-4", "-o", "addr", "show", net.name], capture_output=True, text=True, timeout=2).stdout
            m = re.search(r"inet (\S+)", out)
            result["ip_address"] = m.group(1) if m else None
        except (OSError, subprocess.SubprocessError):
            pass
        if up:
            try:  # iw link works unprivileged
                out = subprocess.run(["iw", "dev", net.name, "link"], capture_output=True, text=True, timeout=2).stdout
                ssid = re.search(r"SSID: (.+)", out)
                dbm = re.search(r"signal: (-?\d+)", out)
                rate = re.search(r"tx bitrate: ([\d.]+)", out)
                result["ssid"] = ssid.group(1).strip() if ssid else None
                if dbm:
                    result["signal_dbm"] = int(dbm.group(1))
                    result["signal_percent"] = max(0, min(100, 2 * (result["signal_dbm"] + 100)))
                result["rate_mbps"] = f"{float(rate.group(1)):g} Mbps" if rate else None  # display string, as on Mi A3
            except (OSError, subprocess.SubprocessError):
                pass
            break
    return result


def docker_info(run: Callable[..., Any] = subprocess.run, docker_cmd: str = "docker") -> dict[str, Any]:
    try:
        proc = run([docker_cmd, "ps", "-a", "--format", "{{json .}}"], capture_output=True, text=True,
                   timeout=3, check=True)
        containers = []
        for line in proc.stdout.splitlines():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            containers.append({"name": item.get("Names"), "image": item.get("Image"),
                               "state": item.get("State"), "status": item.get("Status"),
                               "ports": item.get("Ports")})
        return {"available": True, "containers": containers, "error": None}
    except (OSError, subprocess.SubprocessError) as exc:
        return {"available": False, "containers": [], "error": str(exc)[:160]}


PROTECTED_COMMS = {"s9-dashboard"}
SECRET_RE = re.compile(r"(?i)((?:key|token|secret|passw\w*|auth\w*|credential\w*)[\"']?\s*[=:]\s*)\S+")
KILL_GRACE_S = 4  # SIGKILL only if a SIGTERM to the same process is at least this old
_users: dict[int, str] = {}


def _user_name(uid: int) -> str:
    if uid not in _users:
        try:
            _users[uid] = pwd.getpwuid(uid).pw_name
        except KeyError:
            _users[uid] = str(uid)
    return _users[uid]


def _cmdline(proc_root: Path, pid: int) -> str | None:
    try:
        raw = (proc_root / str(pid) / "cmdline").read_bytes()[:400]
    except OSError:
        return None
    text = raw.replace(b"\0", b" ").decode(errors="replace").strip()
    return SECRET_RE.sub(r"\1***", text)[:80] or None


def process_protected(pid: int, comm: str) -> bool:
    return pid in (1, os.getpid()) or comm in PROTECTED_COMMS


class Collector:
    FEATURE_CACHE_SECONDS = 30

    def __init__(self, proc_root: Path = Path("/proc"), sys_root: Path = Path("/sys"),
                 storage_path: str = "/", cpu_count: int | None = None,
                 run: Callable[..., Any] = subprocess.run) -> None:
        self.proc_root = Path(proc_root)
        self.sys_root = Path(sys_root)
        self.storage_path = storage_path
        self.cpu_count = cpu_count or present_cpus(self.sys_root) or os.cpu_count() or 1
        self.run = run
        self.port = 8090
        self._previous_cpu: tuple[int, int] | None = None
        self._previous_cores: dict[int, tuple[int, int]] = {}
        self._previous_processes: dict[int, tuple[int, int, str, int]] = {}
        self._feature_cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._lock = threading.Lock()
        self._termed: dict[tuple[int, int], float] = {}

    def _feature(self, key: str, loader: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        now = time.monotonic()
        cached = self._feature_cache.get(key)
        if cached and now - cached[0] < self.FEATURE_CACHE_SECONDS:
            return cached[1]
        value = loader()
        self._feature_cache[key] = (time.monotonic(), value)
        return value

    def collect(self) -> dict[str, Any]:
        with self._lock:
            current_cpu = _cpu_totals(self.proc_root)
            current_processes = _process_snapshot(self.proc_root)
            cpu_percent: float | None = None
            process_rows: list[dict[str, Any]] = []
            total_delta = 0
            if current_cpu and self._previous_cpu:
                total_delta = current_cpu[0] - self._previous_cpu[0]
                busy_delta = current_cpu[1] - self._previous_cpu[1]
                if total_delta > 0:
                    cpu_percent = round(max(0, min(100, busy_delta * 100 / total_delta)), 1)
            memory_total = memory_info(self.proc_root).get("total_bytes")
            cores = _core_totals(self.proc_root)  # online only: total_delta sums these
            for pid, (start, ticks, comm, rss) in current_processes.items():
                previous = self._previous_processes.get(pid)
                process_cpu = None
                if total_delta > 0 and previous and previous[0] == start:
                    process_cpu = round(max(0, ticks - previous[1]) * len(cores) * 100 / total_delta, 1)
                process_rows.append({"pid": pid, "name": comm, "cpu_percent": process_cpu,
                                     "rss_bytes": rss,
                                     "memory_percent": round(rss * 100 / memory_total, 1)
                                     if memory_total else None})
            core_percent = [round(max(0, min(100, (c[1] - p[1]) * 100 / (c[0] - p[0]))), 1)
                            if (c := cores.get(n)) and (p := self._previous_cores.get(n)) and c[0] > p[0] else None
                            for n in range(self.cpu_count)]  # None = offline
            self._previous_cores = cores
            self._previous_cpu = current_cpu
            self._previous_processes = current_processes
            process_rows.sort(key=lambda row: (row["cpu_percent"] is not None,
                                               row["cpu_percent"] or 0,
                                               row["rss_bytes"]), reverse=True)
            me = os.getuid()
            for row in process_rows:
                try:
                    uid = os.stat(self.proc_root / str(row["pid"])).st_uid
                except OSError:
                    uid = -1
                row["start"] = current_processes[row["pid"]][0]
                row["user"] = _user_name(uid) if uid >= 0 else "?"
                row["killable"] = uid == me and not process_protected(row["pid"], row["name"])
            for row in process_rows[:30] + sorted(process_rows, key=lambda r: -r["rss_bytes"])[:30]:
                row["cmd"] = _cmdline(self.proc_root, row["pid"])
            parts = partitions(self.sys_root, self.proc_root)
            storage = storage_total(parts) if any(r.get("total_bytes") for r in parts) else _disk(self.storage_path)
            return {
                "collected_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                "battery": battery_info(self.sys_root),
                "gpu": {**gpu_info(self.sys_root), "temp_c": zone_max(self.sys_root, ("G3D",))},
                "services": services_info(self.run),
                "login_user": pwd.getpwuid(os.getuid()).pw_name,
                "uptime_seconds": uptime_seconds(self.proc_root),
                "cpu": {"percent": cpu_percent, "logical_cores": self.cpu_count,
                        "process_percent_basis": "one core = 100%", "cores": core_percent,
                        "temp_c": zone_max(self.sys_root, ("BIG", "LITTLE")),
                        "freq_mhz": cpu_freqs_mhz(self.sys_root), "loadavg": loadavg(self.proc_root)},
                "thermals": thermals(self.sys_root),
                "memory": memory_info(self.proc_root),
                "storage": {**storage, "partitions": parts},
                                "wifi": self._feature("wifi", wifi_info),
                "processes": process_rows,
                "containers": self._feature("docker", lambda: docker_info(self.run)),
            }


    def kill(self, pid: Any, start: Any, sig: Any) -> tuple[bool, str]:
        """SIGTERM, or SIGKILL once a SIGTERM to the same process is old enough. Own processes only."""
        if not (isinstance(pid, int) and not isinstance(pid, bool) and isinstance(start, int)) or sig not in ("TERM", "KILL"):
            return False, "bad request"
        proc = _process_snapshot_one(self.proc_root, pid)
        if proc is None or proc[0] != start:
            return False, "process is gone"
        if process_protected(pid, proc[1]):
            return False, "protected process"
        if os.stat(self.proc_root / str(pid)).st_uid != os.getuid():
            return False, "not your process"
        now = time.monotonic()
        if sig == "KILL" and now - self._termed.get((pid, start), now) < KILL_GRACE_S:
            return False, "send SIGTERM first and wait"
        try:
            os.kill(pid, signal.SIGTERM if sig == "TERM" else signal.SIGKILL)
        except OSError as exc:
            return False, str(exc)[:80]
        if sig == "TERM":
            self._termed[(pid, start)] = now
        return True, f"SIG{sig} sent to {proc[1]} ({pid})"


    DOCKER_ACTIONS = {"pause": ("running",), "unpause": ("paused",), "stop": ("running", "paused"),
                      "start": ("exited", "created")}

    def docker_action(self, action: str, name: Any) -> tuple[bool, str]:
        states = self.DOCKER_ACTIONS.get(action)
        if states is None or not isinstance(name, str):
            return False, "bad request"
        listing = docker_info(self.run, "docker")
        match = next((c for c in listing["containers"] if c["name"] == name), None)
        if match is None:
            return False, "unknown container"
        if (match["state"] or "").lower() not in states:
            return False, f"cannot {action} a {match['state']} container"
        try:
            proc = self.run(["docker", action, name], capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.SubprocessError) as exc:
            return False, str(exc)[:80]
        self._feature_cache.pop("docker", None)
        return (True, f"{action} {name}: ok") if proc.returncode == 0 else (False, (proc.stderr or "failed").strip()[:80])


    def tailscale_login(self) -> tuple[bool, str]:
        """Start `tailscale up` and return its auth URL (allowed via /etc/sudoers.d/s9-tailscale; operator mode is denied by tailscaled here)."""
        def status() -> dict[str, Any]:
            try:
                out = self.run(["tailscale", "status", "--json"], capture_output=True, text=True, timeout=3)
                return json.loads(out.stdout) if out.stdout else {}
            except (OSError, subprocess.SubprocessError, ValueError):
                return {}
        st = status()
        if st.get("BackendState") == "Running":
            return False, "already connected"
        if not st.get("AuthURL"):
            try:
                subprocess.Popen(["sudo", "-n", "/usr/bin/tailscale", "up", "--timeout", "10m"], stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            except OSError as exc:
                return False, str(exc)[:80]
            for _ in range(30):
                time.sleep(0.5)
                st = status()
                if st.get("AuthURL") or st.get("BackendState") == "Running":
                    break
        url = st.get("AuthURL") or ""
        if url.startswith("https://"):
            return True, url
        return (True, "connected") if st.get("BackendState") == "Running" else (False, "no login link from tailscale (is tailscaled running?)")

    def tailscale_down(self) -> tuple[bool, str]:
        try:
            proc = self.run(["sudo", "-n", "/usr/bin/tailscale", "down"], capture_output=True, text=True, timeout=15)
        except (OSError, subprocess.SubprocessError) as exc:
            return False, str(exc)[:80]
        return (True, "off") if proc.returncode == 0 else (False, (proc.stderr or "failed").strip()[:80])


def _process_snapshot_one(proc_root: Path, pid: int) -> tuple[int, str] | None:
    one = _process_snapshot_pid(proc_root, pid)
    return (one[0], one[2]) if one else None


class DashboardHandler(BaseHTTPRequestHandler):
    collector: Collector
    html_path: Path

    def do_GET(self) -> None:
        if self.path == "/api/status":
            body = json.dumps(self.collector.collect(), separators=(",", ":")).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
        elif self.path == "/" or self.path == "/index.html":
            try:
                body = self.html_path.read_bytes()
            except OSError:
                self._send(500, b"Dashboard page is unavailable", "text/plain; charset=utf-8")
                return
            self._send(200, body, "text/html; charset=utf-8")
        else:
            self._send(404, b"Not found", "text/plain; charset=utf-8")

    def do_POST(self) -> None:
        # CSRF guard: same-origin JSON only (a cross-site page can't send application/json without a preflight).
        origin = self.headers.get("Origin") or self.headers.get("Referer") or ""
        if not origin or urlsplit(origin).netloc != self.headers.get("Host", "\0"):
            return self._json(403, False, "bad origin")
        if (self.headers.get("Content-Type") or "").split(";")[0].strip() != "application/json":
            return self._json(415, False, "json only")
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length)) if 0 < length <= 4096 else None
        except (ValueError, OSError):
            body = None
        if not isinstance(body, dict):
            return self._json(400, False, "bad request")
        if self.path == "/api/process/kill":
            ok, msg = self.collector.kill(body.get("pid"), body.get("start"), body.get("signal"))
        elif self.path == "/api/tailscale/login":
            ok, msg = self.collector.tailscale_login()
        elif self.path == "/api/tailscale/down":
            ok, msg = self.collector.tailscale_down()
        elif self.path.startswith("/api/docker/"):
            ok, msg = self.collector.docker_action(self.path[len("/api/docker/"):], body.get("name"))
        else:
            return self._json(404, False, "not found")
        self._json(200 if ok else 409, ok, msg)

    def _json(self, status: int, ok: bool, msg: str) -> None:
        self._send(status, json.dumps({"ok": ok, "message": msg}).encode(), "application/json; charset=utf-8")

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; frame-src http://*:7681")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        pass


def main() -> None:
    try:
        Path("/proc/self/comm").write_text("s9-dashboard")
    except OSError:
        pass
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8090)
    args = parser.parse_args()
    handler = type("S9DashboardHandler", (DashboardHandler,), {
        "collector": Collector(), "html_path": Path(__file__).with_name("index.html")
    })
    handler.collector.port = args.port
    # No firewall (no nftables/iptables on this phone): reachable on every interface, read-only except same-origin kill POSTs.
    server = ThreadingHTTPServer(("0.0.0.0", args.port), handler)
    server.daemon_threads = True
    print(f"S9 dashboard listening on :{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
