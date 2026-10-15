#!/usr/bin/env python3
"""Host-side: render the postmarketOS emblem + wordmark on black into bootlogo/logo.raw.gz (a full-width band of
RGBX rows, 1440 px wide; show.py centres it on the 1440x2960 panel). Needs ImageMagick (`magick`) and Pillow."""
import gzip
import subprocess
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

HERE, W, BAND_H, EMBLEM = Path(__file__).parent, 1440, 900, 520
FONT = '/usr/share/fonts/google-noto/NotoSans-Bold.ttf'   # any bold sans; pass another path as argv[1]

png = HERE / '_emblem.png'
subprocess.run(['magick', '-background', 'none', '-density', '600', str(HERE / 'postmarketos-logo.svg'),
                '-resize', f'{EMBLEM}x{EMBLEM}', str(png)], check=True)
band = Image.new('RGB', (W, BAND_H), 'black')
emblem = Image.open(png).convert('RGBA')
band.paste(emblem, ((W - emblem.width) // 2, 40), emblem)
png.unlink()
d, f = ImageDraw.Draw(band), ImageFont.truetype(sys.argv[1] if len(sys.argv) > 1 else FONT, 130)
d.text((W // 2, 700), 'postmarketOS', fill='#e6edf3', font=f, anchor='mm')
(HERE / 'logo.raw.gz').write_bytes(gzip.compress(band.tobytes('raw', 'RGBX'), 9))
band.save(HERE / 'preview.png')
