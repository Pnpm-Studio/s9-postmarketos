#!/usr/bin/env python3
"""Exercise saved receiver settings against a fake sysfs control."""
import subprocess
import tempfile
from pathlib import Path

with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    conf, control = root / 'wireless', root / 'wc_control'
    script = Path(__file__).with_name('wireless-charging.start').read_text()
    script = script.replace('/etc/s9/wireless', str(conf)).replace(
        '/sys/class/power_supply/battery/wc_control', str(control))
    subprocess.run(['sh', '-c', script], check=True)
    assert not control.exists()
    for value, expected in [('on', '1'), ('off', '0')]:
        conf.write_text(f'ENABLED={value}\n')
        subprocess.run(['sh', '-c', script], check=True)
        assert control.read_text().strip() == expected
    conf.write_text('ENABLED=invalid\n')
    assert subprocess.run(['sh', '-c', script], capture_output=True).returncode != 0
    assert control.read_text().strip() == '0'
print('wireless receiver restore settings passed')
