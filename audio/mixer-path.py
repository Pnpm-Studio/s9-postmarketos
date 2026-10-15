#!/usr/bin/env python3
"""Print Samsung mixer_paths.xml settings as `amixer` commands (no Android audio HAL here).
Usage: mixer-path.py mixer_paths.xml [path ...]   # no paths: the top-level defaults only
Pipe into sh: mixer-path.py /etc/s9/mixer_paths.xml media-speaker | sh"""
import shlex
import sys
import xml.etree.ElementTree as ET


def ctls(node, paths):
    for el in node:
        if el.tag == 'ctl':
            yield el.get('name'), el.get('value'), el.get('id')
        elif el.tag == 'path' and len(el) == 0:            # a reference to another path
            yield from ctls(paths[el.get('name')], paths)


def commands(root, names):
    paths = {}
    for p in root.iter('path'):
        if len(p):                                       # first full definition wins, like the HAL
            paths.setdefault(p.get('name'), p)
    out = [] if names else [c for c in ctls([e for e in root if e.tag == 'ctl'], paths)]
    for name in names:
        out += ctls(paths[name], paths)
    return [f"amixer -q -c0 cset name={shlex.quote(n)} {shlex.quote(v)}" if i is None else
            f"amixer -q -c0 cset name={shlex.quote(n)},index=0 -- $(amixer -c0 cget name={shlex.quote(n)} | sed -n 's/.*: values=//p' | "
            f"awk -F, -v i={int(i) + 1} -v v={shlex.quote(v)} 'BEGIN{{OFS=\",\"}} {{$i=v; print}}')"
            for n, v, i in out]


if __name__ == '__main__':
    if sys.argv[1] == '--selftest':
        root = ET.fromstring('<mixer><ctl name="A" value="1"/><path name="d"><ctl name="B" value="On"/></path>'
                             '<path name="m"><path name="d"/><ctl name="C Vol" value="80" id="1"/></path></mixer>')
        assert commands(root, []) == ["amixer -q -c0 cset name=A 1"]
        c = commands(root, ['m'])
        assert c[0] == "amixer -q -c0 cset name=B On" and "'C Vol'" in c[1] and 'i=2' in c[1]
        print('mixer-path ok')
    else:
        print('\n'.join(commands(ET.parse(sys.argv[1]).getroot(), sys.argv[2:])))
