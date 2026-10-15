"""Run the real link-setup block against a fake gadget: never replace existing links."""
import os
from pathlib import Path
import subprocess
import tempfile

source = Path(__file__).with_name('usb-net').read_text()
start = source.index('\techo "Conf 1"')
block = source[start:source.index('\n\techo $B,acm', start)]
for mode in ('ncm', 'rndis'):
    with tempfile.TemporaryDirectory() as tmp:
        gadget = Path(tmp)
        config = gadget / 'configs/c.1'
        (config / 'strings/0x409').mkdir(parents=True)
        (gadget / 'functions/rndis.usb0').mkdir(parents=True)
        rndis = config / 'rndis.usb0'
        rndis.symlink_to(gadget / 'functions/rndis.usb0')
        inode = rndis.lstat().st_ino
        env = dict(os.environ, G=str(gadget), B=mode)
        subprocess.run(['sh', '-eu', '-c', block], env=env, check=True)
        links = {p.name: (p.lstat().st_ino, p.readlink()) for p in config.iterdir() if p.is_symlink()}
        assert rndis.lstat().st_ino == inode
        assert (config / f'{mode}.usb0').is_dir() and (config / 'acm.gs0').is_dir()
        subprocess.run(['sh', '-eu', '-c', block], env=env, check=True)
        assert links == {p.name: (p.lstat().st_ino, p.readlink()) for p in config.iterdir() if p.is_symlink()}
        assert (config / 'strings/0x409/configuration').read_text().strip() == 'Conf 1'
print('USB link setup: NCM/RNDIS, ACM and repeat-call preservation passed')
