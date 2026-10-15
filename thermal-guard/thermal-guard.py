#!/usr/bin/env python3
"""Power the phone off when a sensor stays too hot. Brief spikes are ignored. Also chimes on low battery.

Battery sensors (zone:battery, psy:battery) shut down at BATT_MAX; everything else (BIG/LITTLE/G3D/ISP/ac
zones) at SOC_MAX. "Sustained" = every sample over the limit for HOLD_S seconds. Unplugged at or below LOW_PCT
it plays `s9-chime low` once, again after recharging above LOW_PCT + 5.
Status for dashboards: /run/thermal-guard.status; events survive reboots in /var/log/thermal-guard.log
"""
import glob, json, os, subprocess, sys, time

BATT_MAX = float(os.environ.get("BATT_MAX", 55))   # °C; Li-ion should never sit above ~60
SOC_MAX = float(os.environ.get("SOC_MAX", 100))    # °C; kernel's own CPU critical trip is 110
HOLD_S = float(os.environ.get("HOLD_S", 60))
LOW_PCT = float(os.environ.get("LOW_PCT", 15))     # %; 0 = no low-battery chime
LIMITS = "/var/lib/thermal-guard/limits.json"  # {"batt_max","soc_max","hold_s","low_pct"}, set on the phone UI; overrides env
RANGES = {"BATT_MAX": ("batt_max", 40, 65), "SOC_MAX": ("soc_max", 70, 110), "HOLD_S": ("hold_s", 10, 300),
          "LOW_PCT": ("low_pct", 0, 50)}
EVERY = 5
BATT = "/sys/class/power_supply/battery/"
BATT_HINTS = ("batt",)


def read_c(path, scale):
    try:
        c = int(open(path).read()) / scale
    except (OSError, ValueError):
        return None
    return c if -20 < c < 150 else None  # -40 / huge = unconnected or no battery


def sensors():
    """{name: °C} for every readable temperature."""
    out = {}
    for z in glob.glob("/sys/class/thermal/thermal_zone*"):
        c = read_c(z + "/temp", 1000)
        if c is not None:
            out["zone:" + open(z + "/type").read().strip()] = c
    for f in glob.glob("/sys/class/power_supply/*/temp"):
        c = read_c(f, 10)
        if c is not None:
            out["psy:" + f.split("/")[-2]] = c
    return out


def load_limits(path=LIMITS):
    """Apply limits.json (clamped) over the env defaults; a missing or broken file changes nothing."""
    try:
        c = json.load(open(path))
    except (OSError, ValueError):
        return
    for var, (key, lo, hi) in RANGES.items():
        v = c.get(key) if isinstance(c, dict) else None
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            globals()[var] = float(max(lo, min(hi, v)))


def limit(name):
    return BATT_MAX if any(h in name for h in BATT_HINTS) else SOC_MAX


def update(since, temps, now):
    """Track when each sensor went over its limit; return (since, [(name, °C, limit)] past HOLD_S)."""
    since = {n: since.get(n, now) for n, c in temps.items() if c >= limit(n)}
    return since, [(n, temps[n], limit(n)) for n, t0 in since.items() if now - t0 >= HOLD_S]


LOG = "/var/log/thermal-guard.log"


def note(msg):
    print(msg, flush=True)
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")
            f.flush()
            os.fsync(f.fileno())  # must hit disk before the power goes
    except OSError:
        pass


def chime(sound="alert"):
    try:  # audio/s9-chime, best effort, never blocks the guard
        subprocess.Popen(["/usr/local/bin/s9-chime", sound], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def low_battery(armed, pct, charging):
    """(armed, chime now?): fire once when unplugged at or below LOW_PCT, re-arm above LOW_PCT + 5 or when charging."""
    if pct is None or not LOW_PCT:
        return armed, False
    if charging or pct > LOW_PCT + 5:
        return True, False
    return (False, True) if armed and pct <= LOW_PCT else (armed, False)


def battery():
    try:
        return float(open(BATT + "capacity").read()), open(BATT + "status").read().strip() in ("Charging", "Full")
    except (OSError, ValueError):
        return None, False


def shutdown(why):
    note("powering off: " + why)
    chime()
    subprocess.run(["wall", f"thermal-guard: powering off, {why}"], check=False)
    time.sleep(2)  # let the alert chime play
    subprocess.run(["poweroff"], check=False)
    time.sleep(90)  # orderly shutdown stuck: force it
    open("/proc/sysrq-trigger", "w").write("o")


def main():
    since, armed = {}, True
    load_limits()
    print(f"watching {len(sensors())} sensors: battery {BATT_MAX} °C, soc {SOC_MAX} °C, sustained {HOLD_S:.0f} s, "
          f"low battery {LOW_PCT:.0f} %", flush=True)
    while True:
        load_limits()
        pct, charging = battery()
        armed, low = low_battery(armed, pct, charging)
        if low:
            note(f"battery low: {pct:.0f} %")
            chime("low")
        temps = sensors()
        before = set(since)
        since, over = update(since, temps, time.monotonic())
        for n in set(since) - before:
            note(f"over limit: {n} {temps[n]:.1f} °C (limit {limit(n)} °C)")
        if set(since) - before:
            chime()
        hottest = max(temps.items(), key=lambda kv: kv[1] - limit(kv[0]), default=("none", 0))
        try:
            open("/run/thermal-guard.status", "w").write(f"{hottest[0]} {hottest[1]:.1f} over={len(since)}\n")
        except OSError:
            pass
        if over:
            shutdown(", ".join(f"{n} {c:.1f} °C >= {lim} °C for {HOLD_S:.0f} s" for n, c, lim in over))
            return
        time.sleep(EVERY)


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        s, over = update({}, {"psy:battery": 56, "zone:BIG": 70}, 0)
        assert list(s) == ["psy:battery"] and not over
        s, over = update(s, {"psy:battery": 57}, 59)
        assert not over
        s, over = update(s, {"psy:battery": 57}, 60)
        assert over == [("psy:battery", 57, BATT_MAX)]
        s, _ = update(s, {"psy:battery": 50}, 61)  # dip below resets the clock
        s, over = update(s, {"psy:battery": 57}, 100)
        assert s == {"psy:battery": 100} and not over
        assert limit("zone:battery") == BATT_MAX and limit("zone:G3D") == SOC_MAX and limit("zone:ac") == SOC_MAX
        a, low = low_battery(True, 15, False)
        assert not a and low                                              # fires once ...
        assert low_battery(a, 10, False) == (False, False)                # ... not again while it drains
        assert low_battery(a, 18, False) == (False, False)                # no re-arm inside the hysteresis
        assert low_battery(a, 12, True) == (True, False)                  # plugged in: re-armed
        assert low_battery(True, 50, False) == (True, False) and low_battery(True, None, False) == (True, False)
        import tempfile
        f = tempfile.mktemp()
        open(f, "w").write('{"batt_max": 99, "soc_max": "x", "hold_s": 30, "low_pct": 0}')
        load_limits(f)
        assert (BATT_MAX, SOC_MAX, HOLD_S, LOW_PCT) == (65.0, 100, 30.0, 0.0)
        assert low_battery(True, 1, False) == (True, False)               # 0 = off
        print("ok", sensors() if os.path.exists("/sys/class/thermal") else "")
    else:
        main()
