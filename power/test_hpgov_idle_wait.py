#!/usr/bin/env python3
"""Exercise the patched governor wait using its actual worker function."""
from pathlib import Path
import subprocess
import sys
import tempfile

PATCH = Path(__file__).with_name("11-hpgov-idle-wait.patch")
SOURCE = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/exynos-hotplug_governor.c")

with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    driver = root / "drivers/soc/samsung/exynos-hotplug_governor.c"
    driver.parent.mkdir(parents=True)
    driver.write_bytes(SOURCE.read_bytes())
    subprocess.run(["patch", "--batch", "-p1", "-i", str(PATCH)],
                   cwd=root, check=True, stdout=subprocess.PIPE, text=True)
    source = driver.read_text()

start = source.index("static int exynos_hpgov_do_update_governor(void *data)")
end = source.index("\n}\n\nstatic void __exynos_hpgov_set_disable", start) + 2
worker = source[start:end]

harness = r'''
#include <assert.h>
struct hpgov_data { int event; };
struct { int wait_q, cur_cpu_min, req_cpu_min; } exynos_hpgov;
static int hpgov_lock, hpgov_min_pm_qos;
static int stop_requested, wake_mode, wait_count, wait_state;
static int control_count, trace_count, qos_count;
static struct hpgov_data *active_data;
#define TASK_RUNNING 0
#define TASK_INTERRUPTIBLE 1
#define FAST_HP 1
#define spin_lock_irqsave(lock, flags) ((void)(lock))
#define spin_unlock_irqrestore(lock, flags) ((void)(lock))
#define wait_event_interruptible(wq, condition) ({ \
    (void)(wq); \
    if (!(condition)) { \
        ++wait_count; \
        wait_state = TASK_INTERRUPTIBLE; \
        if (wake_mode == 1) active_data->event = 1; \
        else if (wake_mode == 2) stop_requested = 1; \
        else assert(0); \
    } \
    0; \
})
static int kthread_should_stop(void) { return stop_requested; }
static void exynos_hpgov_control_cpuidle(int min) { (void)min; ++control_count; }
static void trace_hpgov_req_hotplug(long fast, int min) { (void)fast; (void)min; ++trace_count; }
static void pm_qos_update_request_param(int *request, int min, void *fast)
{
    (void)request; (void)min; (void)fast;
    ++qos_count;
    stop_requested = 1;
}
''' + worker + r'''
static void reset_state(void)
{
    stop_requested = wait_count = wait_state = 0;
    control_count = trace_count = qos_count = 0;
    exynos_hpgov.cur_cpu_min = 0;
    exynos_hpgov.req_cpu_min = 6;
}
int main(void)
{
    struct hpgov_data data = { .event = 0 };
    active_data = &data;
    reset_state();
    wake_mode = 1;
    assert(exynos_hpgov_do_update_governor(&data) == 0);
    assert(wait_count == 1 && wait_state == TASK_INTERRUPTIBLE);
    assert(data.event == 0 && exynos_hpgov.cur_cpu_min == 6);
    assert(control_count == 1 && trace_count == 1 && qos_count == 1);

    data.event = 0;
    reset_state();
    wake_mode = 2;
    assert(exynos_hpgov_do_update_governor(&data) == 0);
    assert(wait_count == 1 && wait_state == TASK_INTERRUPTIBLE);
    assert(control_count == 0 && trace_count == 0 && qos_count == 0);
    return 0;
}
'''

with tempfile.TemporaryDirectory() as directory:
    binary = str(Path(directory) / "hpgov-wait-check")
    subprocess.run(
        ["cc", "-std=gnu11", "-Wall", "-Wextra", "-Werror",
         "-Wno-unused-variable", "-x", "c", "-", "-o", binary],
        input=harness, text=True, check=True,
    )
    subprocess.run([binary], check=True)

print("HP governor: event wake processes once; stop wake exits; idle wait is interruptible")
