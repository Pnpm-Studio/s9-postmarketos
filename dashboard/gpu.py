"""Mali-G72 telemetry from the vendor kernel's /sys/class/misc/mali0/device (read-only). clock is 0 while the GPU is suspended."""
from pathlib import Path


def gpu_info(sys_root: Path) -> dict:
    path = Path(sys_root) / 'class/misc/mali0/device'

    def read(name):
        try:
            return (path / name).read_text().strip()
        except (OSError, UnicodeError):
            return None

    def mhz(name):
        try:
            return int(read(name)) / 1000  # kHz -> MHz
        except (ValueError, TypeError):
            return None

    result = dict(available=path.is_dir(), model=None, clock_mhz=None, max_clock_mhz=None,
                  power_state=None, utilization_percent=None, governor=None)
    if not result['available']:
        return result
    freqs = [int(f) / 1000 for f in (read('dvfs_table') or '').split() if f.isdigit()]
    clock = mhz('clock')
    gov = next((l for l in (read('dvfs_governor') or '').splitlines() if 'Current Governor' in l), '')
    try:
        util = int(read('utilization'))
    except (ValueError, TypeError):
        util = None
    result.update(model=((read('gpuinfo') or '').split(' 0x')[0].replace('-', ' ', 1)) or 'Mali GPU',
                  clock_mhz=clock or None,  # 0 = suspended, shown as Idle
                  max_clock_mhz=max(freqs) if freqs else None, freqs_mhz=freqs,
                  power_state='active' if clock else 'suspended', utilization_percent=util,
                  governor=gov.replace('[Current Governor]', '').strip() or None,
                  shader_cores=next((bin(int(l.split(':')[1], 16)).count('1') for l in (read('core_mask') or '').splitlines()
                                     if l.startswith('Available')), None))
    return result


if __name__ == '__main__':
    print(gpu_info(Path('/sys')))
