# print the minimal file set (paths relative to the android tree) for the Mali driver + given ELF roots
import subprocess, sys, os
B = sys.argv[1]
SEARCH = ['vendor/lib64/egl', 'vendor/lib64', 'system/apex/com.android.runtime.release/lib64/bionic',
          'system/apex/com.android.runtime.release/lib64', 'system/lib64']
need = lambda p: [l.split('[')[1].rstrip(']') for l in subprocess.run(['readelf', '-d', p], capture_output=True, text=True).stdout.splitlines() if '(NEEDED)' in l]
todo = sys.argv[2:]
out = {r for r in todo if not os.path.isabs(r)}  # relative roots ship too
while todo:
    p = todo.pop()
    for n in need(p if os.path.isabs(p) else os.path.join(B, p)):
        if n == 'libvulkan.so':
            n = 'libGLES_mali.so'
        for d in SEARCH:
            rel = os.path.join(d, n)
            if os.path.exists(os.path.join(B, rel)):
                if rel not in out:
                    out.add(rel); todo.append(rel)
                break
        else:
            print('MISSING', n, 'for', p, file=sys.stderr)
for r in sorted(out): print(r)
