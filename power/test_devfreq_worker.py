"""Check the patched worker's normal wake and stop wake against its actual C source."""
from pathlib import Path
import subprocess
import sys
import tempfile

source = Path(sys.argv[1]).read_text()
worker = source.split('static int devfreq_change_freq_task(void *data)', 1)[1].split('/*timer callback', 1)[0]
harness = r'''
#include <assert.h>
#define TASK_INTERRUPTIBLE 1
#define TASK_RUNNING 0
struct devfreq { int lock; };
static int stop, waits, updates, stop_after, state;
static int kthread_should_stop(void) { return stop; }
static void set_current_state(int value) { state = value; }
static void schedule(void) { if (++waits == stop_after) stop = 1; }
static void mutex_lock(int *lock) { (void)lock; }
static void mutex_unlock(int *lock) { (void)lock; }
static void update_devfreq(struct devfreq *df) { (void)df; ++updates; }
static int worker(void *data)
'''+worker+r'''
int main(void) {
    struct devfreq df = {0};
    stop_after = 1;
    assert(worker(&df) == 0 && updates == 0 && state == TASK_RUNNING);
    stop = waits = updates = 0;
    stop_after = 2;
    assert(worker(&df) == 0 && updates == 1 && state == TASK_RUNNING);
    return 0;
}
'''
with tempfile.TemporaryDirectory() as tmp:
    binary = str(Path(tmp, 'worker-check'))
    subprocess.run(['cc', '-Wall', '-Wextra', '-Werror', '-x', 'c', '-', '-o', binary], input=harness, text=True, check=True)
    subprocess.run([binary], check=True)
print('Devfreq worker: ordinary wake updates; stop wake exits without updating')
