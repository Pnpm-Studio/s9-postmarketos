#!/usr/bin/env python3
"""Compile the patched quad_freq knob (patch14) from pinned exynos-hotplug_governor.c and check it.
Usage: test_hpgov_quad_freq.py <kernel-src-root>"""
from pathlib import Path
import subprocess
import sys
import tempfile

HERE = Path(__file__).parent
F = "drivers/soc/samsung/exynos-hotplug_governor.c"

with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    (root / F).parent.mkdir(parents=True)
    (root / F).write_bytes((Path(sys.argv[1]) / F).read_bytes())
    for p in ("11-hpgov-idle-wait.patch", "14-hpgov-quad-freq.patch"):
        subprocess.run(["patch", "--batch", "-p1", "-i", str(HERE / p)], cwd=root, check=True, stdout=subprocess.PIPE)
    source = (root / F).read_text()

    def cut(start, end):
        i = source.index(start)
        return source[i:source.index(end, i)]

    code = (cut("static unsigned long get_hpgov_maxfreq(void)", "static int exynos_hpgov_qos_callback")
            + cut("static int exynos_hpgov_set_quad_freq(int val)", "static int exynos_hpgov_set_single_change_ms"))
    harness = r'''
#include <assert.h>
#define EINVAL 22
#define max(a, b) ((a) > (b) ? (a) : (b))
enum { DISABLE, SINGLE, DUAL, TRIPLE, QUAD };
struct cpumask { int n; };
static struct cpumask online_big = { 4 };
static struct {
    int enabled, suspend, boostable, maxfreq_table[5], quad_cap, quad_dt;
    unsigned long qos_max, pol_max;
    struct cpumask big_cpu_mask;
} exynos_hpgov;
static int updates, hotplug_held;
#define cpumask_weight(m) ((m)->n)
#define cpumask_and(d, a, b) (*(d) = online_big)
#define cpumask_empty(m) (!(m)->n)
#define cpumask_first(m) 4
#define cpu_coregroup_mask(c) 0
#define cpu_online_mask 0
static void get_online_cpus(void) { hotplug_held++; }
static void put_online_cpus(void) { hotplug_held--; }
static int cpufreq_update_policy(int cpu) { assert(cpu == 4 && hotplug_held); updates++; return 0; }
''' + code + r'''
int main(void) {
    int t[5] = { 1794000, 2704000, 2314000, 1794000, 1794000 };
    for (int i = 0; i < 5; i++) exynos_hpgov.maxfreq_table[i] = t[i];
    exynos_hpgov.quad_cap = exynos_hpgov.quad_dt = 1794000;
    exynos_hpgov.enabled = 1; exynos_hpgov.qos_max = exynos_hpgov.pol_max = 2704000;
    exynos_hpgov.big_cpu_mask.n = 4;
    assert(get_hpgov_maxfreq() == 1794000);                               /* boot: DT cap */
    assert(exynos_hpgov_set_quad_freq(1690000) == -EINVAL);               /* below DT */
    assert(exynos_hpgov_set_quad_freq(2808000) == -EINVAL);               /* above single max */
    assert(updates == 0);
    assert(exynos_hpgov_set_quad_freq(2704000) == 0 && updates == 1);
    assert(get_hpgov_maxfreq() == 2704000 && !exynos_hpgov.boostable);   /* no boost headroom left */
    assert(exynos_hpgov.maxfreq_table[TRIPLE] == 2704000 && exynos_hpgov.maxfreq_table[DISABLE] == 2704000);
    assert(exynos_hpgov_set_quad_freq(2314000) == 0 && updates == 2);
    assert(get_hpgov_maxfreq() == 2314000 && exynos_hpgov.boostable);
    assert(exynos_hpgov.maxfreq_table[QUAD] == 2704000);                  /* validator table never lowered */
    exynos_hpgov.big_cpu_mask.n = 2;
    assert(get_hpgov_maxfreq() == 2314000);                               /* dual cap untouched */
    exynos_hpgov.enabled = 0;
    assert(get_hpgov_maxfreq() == 2314000);                               /* governor off: quad cap */
    online_big.n = 0;
    assert(exynos_hpgov_set_quad_freq(1794000) == 0 && updates == 2 && !hotplug_held); /* no big core: no update */
    return 0;
}
'''
    (root / "h.c").write_text(harness)
    subprocess.run(["cc", "-Wall", "-Werror", "-Wno-unused-function", "-o", root / "h", root / "h.c"], check=True)
    subprocess.run([root / "h"], check=True)
print("hpgov quad_freq ok")
