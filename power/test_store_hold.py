#!/usr/bin/env python3
"""Compile the patched store-mode hold (patch12) from pinned sec_battery.c and check its decisions.
Usage: test_store_hold.py <kernel-src-root>"""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

PATCH = Path(__file__).with_name("12-store-hold.patch")
SRC = Path(sys.argv[1])

with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    for f in ("drivers/battery_v2/sec_battery.c", "drivers/battery_v2/include/sec_battery.h"):
        (root / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(SRC / f, root / f)
    subprocess.run(["patch", "--batch", "-p1", "-i", str(PATCH)], cwd=root, check=True, stdout=subprocess.PIPE)
    source = (root / "drivers/battery_v2/sec_battery.c").read_text()
    header = (root / "drivers/battery_v2/include/sec_battery.h").read_text()

    start = source.index("\t\tif (battery->capacity >= STORE_MODE_CHARGING_MAX &&")
    end = source.index("\tpower_supply_changed(battery->psy_bat);", start)
    block = source[start:end].rstrip().removesuffix("}")      # drop the enclosing store_mode if's brace
    harness = r'''
#include <assert.h>
enum { GOOD = 1, OVERHEAT = 2 };
#define POWER_SUPPLY_HEALTH_GOOD GOOD
#define POWER_SUPPLY_STATUS_CHARGING 1
#define POWER_SUPPLY_STATUS_DISCHARGING 2
#define POWER_SUPPLY_STATUS_NOT_CHARGING 3
#define SEC_BAT_CHG_MODE_CHARGING 10
#define SEC_BAT_CHG_MODE_CHARGING_OFF 11
#define SEC_BAT_CHG_MODE_BUCK_OFF 12
#define BATT_MISC_EVENT_UNDEFINED_RANGE_TYPE 1
#define BATT_MISC_EVENT_HICCUP_TYPE 2
#define STORE_MODE_CHARGING_MAX 70
#define STORE_MODE_CHARGING_MIN ''' + header.split("#define STORE_MODE_CHARGING_MAX 70\n#define STORE_MODE_CHARGING_MIN ")[1].split()[0] + r'''
struct sec_battery_info { int capacity, health, status, misc_event, charger_mode; };
static void sec_bat_set_charging_status(struct sec_battery_info *b, int s) { b->status = s; }
static int sec_bat_set_charge(struct sec_battery_info *b, int m) { b->charger_mode = m; return 0; }
static void hold(struct sec_battery_info *battery) {
''' + block + r'''
}
static struct sec_battery_info run(int cap, int health, int status, int misc, int mode) {
    struct sec_battery_info b = { cap, health, status, misc, mode };
    hold(&b);
    return b;
}
int main(void) {
    struct sec_battery_info b;
    b = run(70, GOOD, POWER_SUPPLY_STATUS_CHARGING, 0, SEC_BAT_CHG_MODE_CHARGING);       /* reach cap: stop, input stays on */
    assert(b.charger_mode == SEC_BAT_CHG_MODE_CHARGING_OFF && b.status == POWER_SUPPLY_STATUS_DISCHARGING);
    b = run(85, GOOD, POWER_SUPPLY_STATUS_CHARGING, 0, SEC_BAT_CHG_MODE_CHARGING);       /* above cap: no buck-off drain */
    assert(b.charger_mode == SEC_BAT_CHG_MODE_CHARGING_OFF);
    b = run(69, GOOD, POWER_SUPPLY_STATUS_DISCHARGING, 0, SEC_BAT_CHG_MODE_CHARGING_OFF); /* in band: idle */
    assert(b.charger_mode == SEC_BAT_CHG_MODE_CHARGING_OFF && b.status == POWER_SUPPLY_STATUS_DISCHARGING);
    b = run(68, GOOD, POWER_SUPPLY_STATUS_DISCHARGING, 0, SEC_BAT_CHG_MODE_CHARGING_OFF); /* top-up point */
    assert(b.charger_mode == SEC_BAT_CHG_MODE_CHARGING && b.status == POWER_SUPPLY_STATUS_CHARGING);
    b = run(75, GOOD, POWER_SUPPLY_STATUS_CHARGING, BATT_MISC_EVENT_HICCUP_TYPE, SEC_BAT_CHG_MODE_CHARGING);
    assert(b.charger_mode == SEC_BAT_CHG_MODE_BUCK_OFF);                                  /* protection keeps buck-off */
    b = run(75, OVERHEAT, POWER_SUPPLY_STATUS_NOT_CHARGING, 0, SEC_BAT_CHG_MODE_BUCK_OFF);
    assert(b.charger_mode == SEC_BAT_CHG_MODE_BUCK_OFF && b.status == POWER_SUPPLY_STATUS_NOT_CHARGING); /* untouched */
    b = run(60, OVERHEAT, POWER_SUPPLY_STATUS_DISCHARGING, 0, SEC_BAT_CHG_MODE_BUCK_OFF);
    assert(b.charger_mode == SEC_BAT_CHG_MODE_BUCK_OFF);                                  /* no restart while unhealthy */
    return 0;
}
'''
    (root / "h.c").write_text(harness)
    subprocess.run(["cc", "-Wall", "-Werror", "-o", root / "h", root / "h.c"], check=True)
    subprocess.run([root / "h"], check=True)
print("store hold ok")
