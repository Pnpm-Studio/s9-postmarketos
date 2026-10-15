#!/usr/bin/env python3
"""Compile the patched ACPM reply wait (patch13) from pinned acpm_ipc.c and check it.
Usage: test_acpm_recheck.py <kernel-src-root>"""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

PATCH = Path(__file__).with_name("13-acpm-ipc-recheck.patch")
SRC = Path(sys.argv[1])
F = "drivers/soc/samsung/acpm/acpm_ipc.c"

with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    (root / F).parent.mkdir(parents=True)
    shutil.copy(SRC / F, root / F)
    subprocess.run(["patch", "--batch", "-p1", "-i", str(PATCH)], cwd=root, check=True, stdout=subprocess.PIPE)
    source = (root / F).read_text()
    start = source.index("\tif (channel->polling && cfg->response) {")
    end = source.index("\treturn 0;\n}", start)
    harness = r'''
#include <assert.h>
#include <stdbool.h>
typedef unsigned long long u64; typedef unsigned int u32;
#define IPC_TIMEOUT 15000000ULL
#define INTSR1 0
#define ETIMEDOUT 110
struct ipc_config { int response; };
struct acpm_ipc_ch { int polling, id; };
static struct { char intr[4]; int w_mode; } ipc_s, *acpm_ipc = &ipc_s;
static struct { int debug_log_level, update_log_work; } dbg_s, *acpm_debug = &dbg_s;
static u64 clock_now, clock_step, jump, ready_at = ~0ULL; static int calls, retries, bugs;
static u64 sched_clock(void) { clock_now += ++calls == 2 ? jump : clock_step; return clock_now; }   /* call 2 = after a preemption */
static u32 __raw_readl(void *p) { (void)p; return clock_now >= ready_at ? 1 : 0; }
static bool check_response(struct acpm_ipc_ch *c, struct ipc_config *cfg) { (void)c; (void)cfg; return clock_now < ready_at; }
#define pr_err(...) (retries++)
#define usleep_range(a, b)
#define cpu_relax()
#define acpm_log_print()
#define acpm_ramdump()
#define BUG_ON(x) (bugs += !!(x))
#define queue_work(a, b)
static int update_log_wq;
static int wait(u64 step, u64 jmp, u64 ready) {
    struct acpm_ipc_ch ch = { 1, 0 }, *channel = &ch; struct ipc_config c = { 1 }, *cfg = &c;
    bool timeout_flag = 0; u64 timeout, now; u32 retry_cnt = 0;
    clock_now = 0; clock_step = step; jump = jmp; ready_at = ready; calls = retries = bugs = 0;
''' + source[start:end] + r'''
    return 0;
}
int main(void) {
    assert(wait(1000, 1000, 5000) == 0 && retries == 0);               /* normal fast reply */
    assert(wait(1000, 20000000, 10000000) == 0 && retries == 0);       /* preempted past the deadline, reply already in: no retry */
    assert(wait(1000, 20000000, 30000000) == 0 && retries == 1);  /* really late reply: one retry, still logged */
    assert(wait(1000000, 1000000, ~0ULL) == -ETIMEDOUT && bugs == 1);     /* never answers: still retries, then the stock timeout */
    return 0;
}
'''
    (root / "h.c").write_text(harness)
    subprocess.run(["cc", "-Wall", "-Wno-unused-variable", "-Wno-unused-label", "-Werror", "-o", root / "h", root / "h.c"], check=True)
    subprocess.run([root / "h"], check=True)
print("acpm recheck ok")
