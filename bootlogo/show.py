"""Paint logo.raw.gz (full-width RGBX band, see make-logo.py) centred on /dev/fb0 and pan, so the panel shows the
postmarketOS logo from sysinit until s9-display repaints it. Plain stdlib, started with `python3 -S` (~50 ms)."""
import fcntl
import mmap
import os
import struct
import sys
import zlib

fd = os.open('/dev/fb0', os.O_RDWR)
var = bytearray(fcntl.ioctl(fd, 0x4600, bytes(160)))                    # FBIOGET_VSCREENINFO
xres, yres, _, _, _, yoff, bpp = struct.unpack_from('7I', var)
offs = struct.unpack_from('9I', var, 32)
stride = int(open('/sys/class/graphics/fb0/stride').read())
band = zlib.decompress(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logo.raw.gz'), 'rb').read(), 31)
if bpp != 32 or (offs[0], offs[3], offs[6]) != (0, 8, 16) or xres * 4 != stride or len(band) % stride:
    sys.exit('s9-bootlogo: unexpected framebuffer layout, skipped')     # the band is baked as RGBX
at = yoff * stride + (yres - len(band) // stride) // 2 * stride    # write() to this fb returns 0, so mmap like display.py
mm = mmap.mmap(fd, stride * (yoff + yres))
mm[at:at + len(band)] = band
try:
    fcntl.ioctl(fd, 0x4606, bytes(var))                                  # FBIOPAN_DISPLAY: latch the frame
except OSError:
    pass
