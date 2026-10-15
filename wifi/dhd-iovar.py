#!/usr/bin/env python3
"""Get/set a Broadcom dhd driver iovar on wlan0: dhd-iovar.py idletime [VALUE].

idletime 0 disables the PCIe runtime-PM sleep/wake cycle, which otherwise logs
~25 warning lines every few seconds (dhdpcie_bus_suspend, D3 ACK, exynos-pcie ...).
"""
import ctypes, fcntl, socket, struct, sys

SIOCDEVPRIVATE, DHD_GET_VAR, DHD_SET_VAR, DHD_IOCTL_MAGIC = 0x89F0, 2, 3, 0x00444944


def iovar(name, value=None, ifname='wlan0'):
    buf = ctypes.create_string_buffer(name.encode() + b'\0' + struct.pack('<i', value or 0), 64)
    # wl_ioctl_t on aarch64 (cmd, pad, buf*, len, set, used, needed) followed by dhd's driver magic
    ioc = ctypes.create_string_buffer(struct.pack('<IxxxxQIB3xIII', DHD_GET_VAR if value is None else DHD_SET_VAR,
                                                  ctypes.addressof(buf), len(buf), value is not None, 0, 0, DHD_IOCTL_MAGIC))
    ifr = struct.pack('16sQ', ifname.encode(), ctypes.addressof(ioc))
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        fcntl.ioctl(s, SIOCDEVPRIVATE, ifr)
    return struct.unpack('<i', buf.raw[:4])[0]


if __name__ == '__main__':
    if len(sys.argv) > 2:
        iovar(sys.argv[1], int(sys.argv[2]))
    print(iovar(sys.argv[1]))
