import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';
import { createHash } from 'node:crypto';
import { s9 } from '../site/s9-manifest.js';
import { fetchPinned, inspectS9, installRom, installTwrp, selectRomImages, selectTwrp, ROM_CONFIRMATION, TWRP_CONFIRMATION } from '../site/s9.js';

const original = structuredClone(s9);
afterEach(() => { Object.assign(s9, structuredClone(original)); });
const sha = data => createHash('sha256').update(data).digest('hex');

// ---- Section 1 ----
function twrpFixture() {
  const file = new File(['twrp-bytes'], s9.twrp.name);
  s9.twrp.size = file.size;
  s9.twrp.sha256 = sha('twrp-bytes');
  const calls = [];
  const entries = Object.fromEntries(['BOOT', 'SYSTEM', 'VENDOR', 'USERDATA', 'RECOVERY'].map(n => [n, { partitionSize: 1 << 20 }]));
  const odin = {
    async beginSession() { calls.push('begin'); },
    async getPitData() { calls.push('pit'); return { findEntryByName: n => entries[n] }; },
    async flashPartition(name) { calls.push(`flash:${name}`); },
    async reboot() { calls.push('reboot'); }
  };
  return { file, odin, calls, entries };
}
const twrpConsent = { consent: true, confirmation: TWRP_CONFIRMATION };

test('TWRP: only RECOVERY is written and the phone is never rebooted', async () => {
  const { file, odin, calls } = twrpFixture();
  await installTwrp(odin, file, twrpConsent, () => {}, () => {});
  assert.deepEqual(calls, ['begin', 'pit', 'flash:RECOVERY']);
});

test('TWRP: wrong name/size/hash, consent, odd PIT or small RECOVERY write nothing', async () => {
  for (const reason of ['name', 'hash', 'consent', 'pit', 'no-recovery', 'small']) {
    const { file, odin, calls, entries } = twrpFixture();
    let input = file;
    let consent = twrpConsent;
    if (reason === 'name') input = new File(['twrp-bytes'], 'other.img');
    if (reason === 'hash') s9.twrp.sha256 = '0'.repeat(64);
    if (reason === 'consent') consent = { ...twrpConsent, confirmation: 'nope' };
    if (reason === 'pit') delete entries.VENDOR;
    if (reason === 'no-recovery') delete entries.RECOVERY;
    if (reason === 'small') entries.RECOVERY.partitionSize = 1;
    await assert.rejects(installTwrp(odin, input, consent, () => {}, () => {}), undefined, reason);
    assert.ok(!calls.includes('flash:RECOVERY'), reason);
  }
  assert.throws(() => selectTwrp([]), /exactly/);
});

// ---- Section 2 ----
const contents = { 'samsung-starlte-root.img': 'ROOT-DATA', 'samsung-starlte-boot.img': 'BOOT-PART', 'boot.img': 'KERNEL' };
function romFixture() {
  const files = s9.images.map(image => new File([contents[image.name]], image.name));
  s9.release = 'test';
  s9.images.forEach((image, i) => { image.size = files[i].size; image.sha256 = sha(contents[image.name]); });
  const calls = [];
  const disk = {};
  const state = { product: 'starlte', twrp: '3.7.0', mounts: '/dev/block/sda1 /data ext4 rw 0 0', size: 1 << 30, mke2fs: true, corrupt: false };
  const shell = {
    async run(command) {
      calls.push(command);
      if (command === 'getprop ro.product.device') return { code: 0, out: state.product + '\n' };
      if (command === 'getprop ro.twrp.version') return { code: 0, out: state.twrp + '\n' };
      if (command === 'cat /proc/mounts') return { code: 0, out: state.mounts };
      if (command.startsWith('test -b')) return { code: 0, out: '' };
      if (command.startsWith('readlink -f')) return { code: 0, out: '/dev/block/sdq' + command.length + '\n' };
      if (command.startsWith('blockdev')) return { code: 0, out: `${state.size}\n` };
      if (command === 'command -v mke2fs') return { code: state.mke2fs ? 0 : 1, out: '' };
      if (command.startsWith('head -c')) {
        const [, size, path] = command.match(/head -c (\d+) (\S+) \|/);
        const data = disk[path] ?? '';
        return { code: 0, out: `${sha(state.corrupt ? 'bad' : data.slice(0, Number(size)))}  -\n` };
      }
      return { code: 0, out: '' };
    },
    async pipe(command, file) {
      calls.push(command);
      disk[command.match(/of=(\S+)/)[1]] = await file.text();
      return { code: 0, out: '' };
    }
  };
  return { files, calls, state, shell, disk };
}
const opts = { consent: true, confirmation: ROM_CONFIRMATION, formatUserdata: false, reboot: true };
const writes = calls => calls.filter(c => c.startsWith('dd '));

test('ROM: pins left as placeholders fail closed', () => {
  s9.images.forEach(image => { image.size = 0; image.sha256 = ''; });
  assert.throws(() => selectRomImages([]), /not filled in/);
});

test('ROM: writes SYSTEM, VENDOR, BOOT in order, verifies each, then reboots', async () => {
  const { shell, files, calls, disk } = romFixture();
  await installRom(shell, selectRomImages(files).map(i => ({ ...i })), opts, () => {}, () => {});
  const by = s9.byName;
  assert.deepEqual(writes(calls), [`dd of=${by}/SYSTEM bs=1048576`, `dd of=${by}/VENDOR bs=1048576`, `dd of=${by}/BOOT bs=1048576`]);
  assert.equal(disk[`${by}/SYSTEM`], 'ROOT-DATA');
  assert.equal(calls.filter(c => c.startsWith('head -c')).length, 3);
  assert.equal(calls.at(-1), 'reboot');
  assert.ok(!calls.some(c => c.includes('USERDATA') && c.startsWith('dd')));
  assert.ok(!calls.some(c => c.startsWith('mke2fs')));
});

test('ROM: optional USERDATA format runs after verification, before reboot', async () => {
  const { shell, files, calls } = romFixture();
  await installRom(shell, selectRomImages(files).map(i => ({ ...i })), { ...opts, formatUserdata: true }, () => {}, () => {});
  assert.deepEqual(calls.slice(-2), [`mke2fs -F -t ext4 -L s9-srv ${s9.byName}/USERDATA`, 'reboot']);
});

test('ROM: auto-mounted USERDATA does not block a normal flash, is unmounted before format, and blocks if it stays mounted', async () => {
  const a = romFixture();
  const run = a.shell.run;
  const data = '/dev/block/sdq' + `readlink -f ${s9.byName}/USERDATA`.length;
  a.shell.run = async c => c === 'cat /proc/mounts' ? { code: 0, out: `${data} /data ext4 rw 0 0` } : run(c);
  await installRom(a.shell, selectRomImages(a.files).map(i => ({ ...i })), opts, () => {}, () => {});
  assert.ok(!a.calls.some(c => c.startsWith('umount')));
  const b = romFixture();
  let mounted = true;
  const run2 = b.shell.run;
  b.shell.run = async c => {
    if (c.startsWith('umount')) { b.calls.push(c); mounted = false; return { code: 0, out: '' }; }
    return c === 'cat /proc/mounts' && mounted ? { code: 0, out: `${data} /data ext4 rw 0 0` } : run2(c);
  };
  await installRom(b.shell, selectRomImages(b.files).map(i => ({ ...i })), { ...opts, formatUserdata: true }, () => {}, () => {});
  assert.deepEqual(b.calls.slice(-5, -1).filter(c => c.startsWith('umount')), ['umount /sdcard', 'umount /data']);
  const c = romFixture();
  const run3 = c.shell.run;
  c.shell.run = async x => x === 'cat /proc/mounts' ? { code: 0, out: `${data} /data ext4 rw 0 0` } : run3(x);
  await assert.rejects(installRom(c.shell, selectRomImages(c.files).map(i => ({ ...i })), { ...opts, formatUserdata: true }, () => {}, () => {}), /still mounted/);
  assert.ok(!c.calls.some(x => x.startsWith('mke2fs') || x === 'reboot'));
});

test('ROM: wrong phone, no TWRP, mounted partition, small partition, no mke2fs or bad consent write nothing', async () => {
  for (const reason of ['product', 'twrp', 'mounted', 'small', 'mke2fs', 'hash', 'consent']) {
    const { shell, files, calls, state } = romFixture();
    let options = opts;
    if (reason === 'product') state.product = 'starqltechn';
    if (reason === 'twrp') state.twrp = '';
    if (reason === 'mounted') state.mounts = '/dev/block/sdq' + `readlink -f ${s9.byName}/SYSTEM`.length + ' /system ext4 rw 0 0';
    if (reason === 'small') state.size = 4;
    if (reason === 'mke2fs') { state.mke2fs = false; options = { ...opts, formatUserdata: true }; }
    if (reason === 'hash') s9.images[1].sha256 = '0'.repeat(64);
    if (reason === 'consent') options = { ...opts, consent: false };
    await assert.rejects(installRom(shell, selectRomImages(files).map(i => ({ ...i })), options, () => {}, () => {}), undefined, reason);
    assert.deepEqual(writes(calls), [], reason);
  }
});

test('ROM: read-back mismatch stops before the next write, format or reboot', async () => {
  const { shell, files, calls, state } = romFixture();
  state.corrupt = true;
  await assert.rejects(installRom(shell, selectRomImages(files).map(i => ({ ...i })), { ...opts, formatUserdata: true }, () => {}, () => {}), /read back wrong/);
  assert.equal(writes(calls).length, 1);
  assert.ok(!calls.includes('reboot') && !calls.some(c => c.startsWith('mke2fs')));
});

test('ROM: dd failure and lost session stop immediately', async () => {
  const a = romFixture();
  a.shell.pipe = async command => { a.calls.push(command); return { code: 1, out: 'No space' }; };
  await assert.rejects(installRom(a.shell, selectRomImages(a.files).map(i => ({ ...i })), opts, () => {}, () => {}), /dd to SYSTEM failed/);
  assert.equal(writes(a.calls).length, 1);
  const b = romFixture();
  await assert.rejects(installRom(b.shell, selectRomImages(b.files).map(i => ({ ...i })), opts, () => {}, () => {
    if (writes(b.calls).length > 0) throw Error('session lost');
  }), /session lost/);
  assert.equal(writes(b.calls).length, 1);
});

test('inspectS9 rejects non-block paths', async () => {
  const { shell } = romFixture();
  const run = shell.run;
  shell.run = async c => c.startsWith('test -b') ? { code: 1, out: '' } : run(c);
  await assert.rejects(inspectS9(shell), /not a block device/);
});

test('streaming SHA-256 matches the standard implementation, including empty input', async () => {
  const { checksum } = await import('../site/hash.js');
  for (const value of ['', 'hello', 'x'.repeat(5 * 1024 * 1024)]) {
    assert.equal(await checksum(new Blob([value])), sha(value));
  }
});

test('fetchPinned returns a named File of the pinned size and rejects missing or wrong-size downloads', async () => {
  const serve = (body, status = 200) => async () => new Response(body, { status });
  const file = await fetchPinned({ name: 'boot.img', size: 5 }, () => {}, serve('hello'));
  assert.equal(file.name, 'boot.img');
  assert.equal(await file.text(), 'hello');
  await assert.rejects(fetchPinned({ name: 'boot.img', size: 5 }, () => {}, serve('nope', 404)), /could not be downloaded/);
  const urls = [];
  const mirrored = await fetchPinned({ name: 'boot.img', size: 5 }, () => {},
    async url => { urls.push(url); return url.startsWith('./') ? new Response('', { status: 404 }) : new Response('hello'); });
  assert.equal(await mirrored.text(), 'hello');
  assert.deepEqual(urls, ['./boot.img', `${s9.mirror}${s9.release}/boot.img`]);
  await assert.rejects(fetchPinned({ name: 'boot.img', size: 5 }, () => {}, serve('hell')), /pinned 5/);
  await assert.rejects(fetchPinned({ name: 'boot.img', size: 5 }, () => {}, serve('hello!')), /larger/);
});

test('useModel switches every pin to the S9+ and back', async () => {
  const { models, useModel } = await import('../site/s9-manifest.js');
  const saved = { ...s9 };
  try {
    useModel('star2lte');
    assert.equal(s9.device, 'star2lte');
    assert.equal(s9.twrp.name, 'twrp-3.7.0_9-0-star2lte.img');
    assert.deepEqual(s9.images.map(i => i.name), ['samsung-star2lte-root.img', 'samsung-star2lte-boot.img', 'boot.img']);
    useModel('nonsense');
    assert.equal(s9.device, 'star2lte');
    // an S9 in TWRP must be refused while the S9+ is picked
    const shell = { run: async () => ({ code: 0, out: 'starlte' }) };
    await assert.rejects(inspectS9(shell), /Expected star2lte; phone reports starlte/);
    useModel('starlte');
    assert.equal(s9.twrp.name, models.starlte.twrp.name);
  } finally { Object.assign(s9, saved); }
});
