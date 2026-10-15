#!/usr/bin/env python3
"""UNACCEPTED candidate: host-check exact C; CHARGE_DISABLE protection case currently fails."""
from pathlib import Path
import subprocess
import sys
import tempfile

source = Path(sys.argv[1] if len(sys.argv) > 1 else '/tmp/s9-sec_battery-patched.c').read_text()


def block(marker):
    start = source.index(marker)
    brace = source.index('{', start)
    depth = 0
    for index in range(brace, len(source)):
        depth += (source[index] == '{') - (source[index] == '}')
        if not depth:
            return source[start:index + 1]
    raise ValueError(marker)


helpers = block('static bool sec_bat_store_mode_hold(') + '\n' + block('static bool sec_bat_store_mode_healthy(')
charge = block('int sec_bat_set_charge(')
cap = block('if (sec_bat_store_mode_hold(battery) && sec_bat_store_mode_healthy(battery)')
wire = block('if (battery->store_mode) {\n\t\tswitch (battery->wire_status)')
status_start = source.index('if ((status == POWER_SUPPLY_STATUS_CHARGING || status == POWER_SUPPLY_STATUS_FULL)')
status_guard = source[status_start:source.index(';', status_start) + 1]
# Fail if cap pause again bypasses upstream safety checks or induces fake recovery.
assert '(battery->status == POWER_SUPPLY_STATUS_NOT_CHARGING &&\n\t     !(battery->store_charge_paused && sec_bat_store_mode_healthy(battery)))' in source
assert '(!battery->store_charge_paused || battery->is_abnormal_temp)' in source
assert 'battery->store_charge_paused = false;\n\t\tbattery->charging_mode' in source
for field in ('current_max', 'input_current', 'charging_current'):
    assert f'battery->{field}' not in helpers + cap + wire

harness = r'''
#include <assert.h>
#include <stdbool.h>
#include <time.h>
#define CONFIG_BATTERY_SWELLING 1
#define STORE_MODE_CHARGING_MAX 70
#define STORE_MODE_CHARGING_MIN 60
#define BATT_MISC_EVENT_UNDEFINED_RANGE_TYPE 1
#define BATT_MISC_EVENT_HICCUP_TYPE 2
#define SEC_BAT_CURRENT_EVENT_CHARGE_DISABLE 1
#define SEC_BAT_CURRENT_EVENT_VBAT_OVP 2
#define SEC_BAT_CURRENT_EVENT_VSYS_OVP 4
#define POWER_SUPPLY_HEALTH_GOOD 1
#define POWER_SUPPLY_STATUS_DISCHARGING 1
#define POWER_SUPPLY_STATUS_CHARGING 2
#define POWER_SUPPLY_STATUS_NOT_CHARGING 3
#define POWER_SUPPLY_STATUS_FULL 4
#define SEC_BAT_CHG_MODE_CHARGING 10
#define SEC_BAT_CHG_MODE_CHARGING_OFF 11
#define SEC_BAT_CHG_MODE_BUCK_OFF 12
#define SWELLING_MODE_NONE 0
enum { SEC_BATTERY_CABLE_UNKNOWN, SEC_BATTERY_CABLE_NONE,
 SEC_BATTERY_CABLE_PREPARE_TA, SEC_BATTERY_CABLE_TA, SEC_BATTERY_CABLE_USB,
 SEC_BATTERY_CABLE_USB_CDP, SEC_BATTERY_CABLE_9V_TA, SEC_BATTERY_CABLE_9V_ERR,
 SEC_BATTERY_CABLE_9V_UNKNOWN, SEC_BATTERY_CABLE_12V_TA,
 SEC_BATTERY_CABLE_WIRELESS, SEC_BATTERY_CABLE_HV_WIRELESS,
 SEC_BATTERY_CABLE_QC20, SEC_BATTERY_CABLE_QC30, SEC_BATTERY_CABLE_PDIC,
 SEC_BATTERY_CABLE_HV_TA_CHG_LIMIT, SEC_BATTERY_CABLE_HMT_CONNECTED,
 SEC_BATTERY_CABLE_OTG, SEC_BATTERY_CABLE_POWER_SHARING };
union power_supply_propval { int intval; };
typedef struct { long tv_sec; } ktime_t;
struct pdata { int charging_reset_time; };
struct sec_battery_info {
 int capacity, misc_event, current_event, health, status, slate_mode, store_mode;
 int store_charge_paused, cable_type, wire_status, swelling_mode, charger_mode;
 int is_abnormal_temp, is_sysovlo, is_vbatovlo, charging_block;
 int charging_start_time, charging_next_time, charging_passed_time;
 int charging_fullcharged_time, full_check_cnt;
 int temp_highlimit_cnt, temp_high_cnt, temp_low_cnt, temp_recover_cnt;
 struct pdata *pdata;
};
static int hardware_calls, hardware_mode;
#define pr_info(...) ((void)0)
#define dev_info(...) ((void)0)
#define psy_do_property(name, action, prop, value) do { \
 hardware_calls++; hardware_mode = (value).intval; } while (0)
static ktime_t ktime_get_boottime(void) { return (ktime_t){100}; }
static struct timespec ktime_to_timespec(ktime_t t) { return (struct timespec){t.tv_sec, 0}; }
static int is_nocharge_type(int c) { return c == SEC_BATTERY_CABLE_NONE ||
 c == SEC_BATTERY_CABLE_OTG || c == SEC_BATTERY_CABLE_POWER_SHARING; }
static int is_slate_mode(struct sec_battery_info *b) { return b->slate_mode; }
''' + helpers + r'''
static void sec_bat_set_charging_status(struct sec_battery_info *battery, int status)
{
''' + status_guard + r'''
 battery->status = status;
}
''' + charge + r'''
static void monitor_cap(struct sec_battery_info *battery)
{
''' + cap + r'''
}
static int cable(struct sec_battery_info *battery, int current_cable_type)
{
''' + wire + r'''
 return current_cable_type;
}
static struct sec_battery_info fresh(int capacity, int type)
{
 static struct pdata pdata = { 1000 };
 return (struct sec_battery_info){ .capacity=capacity, .store_mode=1,
 .health=POWER_SUPPLY_HEALTH_GOOD, .status=POWER_SUPPLY_STATUS_CHARGING,
 .charger_mode=SEC_BAT_CHG_MODE_CHARGING, .cable_type=type, .pdata=&pdata };
}
int main(void)
{
 struct sec_battery_info b;
 int types[] = { SEC_BATTERY_CABLE_USB, SEC_BATTERY_CABLE_WIRELESS };
 for (unsigned i=0; i<2; i++) {
  for (int soc=70; soc<=71; soc++) {
   b=fresh(soc, types[i]); monitor_cap(&b);
   assert(b.status==POWER_SUPPLY_STATUS_NOT_CHARGING);
   assert(b.charger_mode==SEC_BAT_CHG_MODE_CHARGING_OFF && b.store_charge_paused);
   b.temp_high_cnt=2; hardware_calls=0;
   monitor_cap(&b); sec_bat_set_charge(&b, SEC_BAT_CHG_MODE_CHARGING);
   assert(b.temp_high_cnt==2 && hardware_calls==0);
   b.capacity=61; monitor_cap(&b); assert(b.store_charge_paused);
   b.capacity=60; monitor_cap(&b);
   assert(!b.store_charge_paused && b.charger_mode==SEC_BAT_CHG_MODE_CHARGING);
  }
 }
 // Every independent protection prevents cap policy from overriding BUCK_OFF or resuming.
 for (int fault=0; fault<9; fault++) {
  b=fresh(71, SEC_BATTERY_CABLE_USB); b.store_charge_paused=1;
  b.charger_mode=SEC_BAT_CHG_MODE_BUCK_OFF;
  if (fault==0) b.swelling_mode=1;
  if (fault==1) b.health=2;
  if (fault==2) b.misc_event=BATT_MISC_EVENT_HICCUP_TYPE;
  if (fault==3) b.misc_event=BATT_MISC_EVENT_UNDEFINED_RANGE_TYPE;
  if (fault==4) b.slate_mode=1;
  if (fault==5) b.is_sysovlo=1;
  if (fault==6) b.is_vbatovlo=1;
  if (fault==7) b.is_abnormal_temp=1;
  if (fault==8) b.current_event=SEC_BAT_CURRENT_EVENT_CHARGE_DISABLE;
  hardware_calls=0; monitor_cap(&b); sec_bat_set_charge(&b, SEC_BAT_CHG_MODE_CHARGING);
  assert(b.charger_mode==SEC_BAT_CHG_MODE_BUCK_OFF && !hardware_calls);
  b.capacity=60; monitor_cap(&b); assert(b.store_charge_paused);
 }
 b=fresh(71, SEC_BATTERY_CABLE_USB); monitor_cap(&b);
 sec_bat_set_charge(&b, SEC_BAT_CHG_MODE_BUCK_OFF);
 assert(b.charger_mode==SEC_BAT_CHG_MODE_BUCK_OFF); // protection command always honored
 b.cable_type=SEC_BATTERY_CABLE_NONE;
 assert(!sec_bat_store_mode_hold(&b) && !b.store_charge_paused);
 b=fresh(71, SEC_BATTERY_CABLE_USB); monitor_cap(&b); b.store_mode=0;
 assert(!sec_bat_store_mode_hold(&b));
 b=fresh(60, SEC_BATTERY_CABLE_USB); b.status=POWER_SUPPLY_STATUS_NOT_CHARGING;
 b.charger_mode=SEC_BAT_CHG_MODE_BUCK_OFF; monitor_cap(&b);
 assert(b.charger_mode==SEC_BAT_CHG_MODE_BUCK_OFF); // unrelated pause has no cap latch
 b=fresh(70, SEC_BATTERY_CABLE_USB);
 for (int type=SEC_BATTERY_CABLE_UNKNOWN; type<=SEC_BATTERY_CABLE_POWER_SHARING; type++) {
  b.wire_status=type;
  int selected=cable(&b, SEC_BATTERY_CABLE_WIRELESS);
  bool known=(type>=SEC_BATTERY_CABLE_PREPARE_TA && type<=SEC_BATTERY_CABLE_12V_TA) ||
   (type>=SEC_BATTERY_CABLE_QC20 && type<=SEC_BATTERY_CABLE_HV_TA_CHG_LIMIT);
  assert(selected==(known ? type : SEC_BATTERY_CABLE_WIRELESS));
 }
 b.store_mode=0; b.wire_status=SEC_BATTERY_CABLE_USB;
 assert(cable(&b, SEC_BATTERY_CABLE_WIRELESS)==SEC_BATTERY_CABLE_WIRELESS);
 return 0;
}
'''
with tempfile.TemporaryDirectory() as directory:
    binary = str(Path(directory) / 'stand-power-check')
    subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror', '-x', 'c', '-', '-o', binary], input=harness, text=True, check=True)
    subprocess.run([binary], check=True)
print('Candidate host checks passed; kernel integration and connected protection review remain required')
