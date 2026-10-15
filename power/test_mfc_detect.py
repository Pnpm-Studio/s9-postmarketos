#!/usr/bin/env python3
"""Compile the patched MFC detect gate against its pinned worker source."""
from pathlib import Path
import subprocess
import sys
import tempfile

PATCH = Path(__file__).with_name("10-mfc-detect-transition.patch")
SOURCE = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/s9-mfc-charger.c")

with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    driver = root / "drivers/battery_v2/mfc_charger.c"
    driver.parent.mkdir(parents=True)
    driver.write_bytes(SOURCE.read_bytes())
    subprocess.run(
        ["patch", "--batch", "-p1", "-i", str(PATCH)],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    )
    source = driver.read_text()

start = source.index("static void mfc_wpc_det_work(struct work_struct *work)")
end = source.index("\n}\n\n/* INT_A (BT2AP interrupt) */", start) + 2
worker = source[start:end]
branch = "\n\tif ((charger->wc_w_state == 0) && (wc_w_state == 1)) {"
epilogue = '\n\tpr_info("%s: w(%d to %d)\\n",'
cut = worker.index(branch)
worker = worker[:cut] + worker[worker.index(epilogue, cut):]

harness = r'''
#include <assert.h>
struct mfc_charger_data;
struct work_struct { struct mfc_charger_data *owner; };
struct mfc_platform_data { int wpc_det; };
struct mfc_charger_data {
    struct { struct work_struct work; } wpc_det_work;
    int wc_w_state, chip_id, is_mst_on, mst_off_lock, wpc_wake_lock;
    struct mfc_platform_data *pdata;
};
union power_supply_propval { int intval; };
typedef unsigned char u8;
#define container_of(ptr, type, member) ((ptr)->owner)
#define MFC_CHIP_LSI 1
#define MST_MODE_2 2
#define pr_info(...) ((void)0)
static int sampled_gpio, gpio_reads, i2c_probes, wake_acquires, wake_releases, wake_depth;
static int chip_result;
static int gpio_get_value(int gpio) { (void)gpio; ++gpio_reads; return sampled_gpio; }
static int mfc_get_chip_id(struct mfc_charger_data *charger)
{
    ++i2c_probes;
    charger->chip_id = chip_result;
    return chip_result;
}
static void wake_lock(int *lock) { (void)lock; ++wake_acquires; ++wake_depth; }
static void wake_unlock(int *lock)
{
    (void)lock;
    ++wake_releases;
    assert(--wake_depth >= 0);
}
''' + worker + r'''
static void check_case(int cached, int sample, int chip, int mst, int mst_off,
                       int expected_cached, int expected_i2c, int expected_wake)
{
    struct mfc_platform_data pdata = { .wpc_det = 7 };
    struct mfc_charger_data charger = { .wc_w_state = cached,
        .is_mst_on = mst, .mst_off_lock = mst_off, .pdata = &pdata };
    charger.wpc_det_work.work.owner = &charger;
    sampled_gpio = sample;
    chip_result = chip;
    gpio_reads = i2c_probes = wake_acquires = wake_releases = wake_depth = 0;
    mfc_wpc_det_work(&charger.wpc_det_work.work);
    assert(gpio_reads == 1);
    assert(i2c_probes == expected_i2c);
    assert(wake_acquires == expected_wake && wake_releases == expected_wake);
    assert(wake_depth == 0 && charger.wc_w_state == expected_cached);
}
int main(void)
{
    check_case(0, 0, 0, 0, 0, 0, 0, 0); /* empty startup */
    check_case(1, 1, 0, 0, 0, 1, 0, 0); /* pad remains attached */
    check_case(0, 1, 0, 0, 0, 1, 1, 1); /* attach */
    check_case(1, 0, 0, 0, 0, 0, 1, 1); /* detach */
    check_case(0, 1, 0, MST_MODE_2, 0, 0, 1, 0); /* MST transition guard */
    check_case(0, 1, MFC_CHIP_LSI, MST_MODE_2, 0, 0, 1, 0); /* LSI MST guard */
    check_case(0, 1, MFC_CHIP_LSI, 0, 1, 0, 1, 0); /* LSI off-lock guard */
    return 0;
}
'''

with tempfile.TemporaryDirectory() as directory:
    binary = str(Path(directory) / "mfc-detect-check")
    subprocess.run(
        ["cc", "-std=gnu11", "-Wall", "-Wextra", "-Werror",
         "-Wno-unused-variable", "-x", "c", "-", "-o", binary],
        input=harness,
        text=True,
        check=True,
    )
    subprocess.run([binary], check=True)

print("MFC detect gate: unchanged levels skip I2C; attach/detach and MST guards balance locks")
