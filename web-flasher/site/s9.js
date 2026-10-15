import { checksum } from './hash.js';
import { s9 } from './s9-manifest.js';

export const TWRP_CONFIRMATION = 'FLASH TWRP';
export const ROM_CONFIRMATION = 'ERASE S9';
const MiB = 1024 * 1024;

/** @param {Blob & {name?:string}} file @param {{name:string,size:number,sha256:string}} pin */
function matchesPin(file, pin) {
  return file.name === pin.name && file.size === pin.size;
}

/**
 * Downloads a pinned file (next to this page, else from the release mirror) into a File, so it can go through the
 * same name/size/SHA-256 checks as a picked one. Parts are folded into Blobs every 64 MiB so the browser
 * can page them to disk instead of holding ~1.3 GB of images in RAM.
 * @param {{name:string,size:number}} pin @param {(fraction:number)=>void} progress @param {typeof fetch} get
 */
export async function fetchPinned(pin, progress = () => {}, get = fetch) {
  const name = encodeURIComponent(pin.name);
  let response = await get(`./${name}`, { cache: 'no-store' });
  if (!response.ok && s9.mirror) response = await get(`${s9.mirror}${encodeURIComponent(s9.release)}/${name}`);
  if (!response.ok || !response.body) throw Error(`${pin.name} could not be downloaded (HTTP ${response.status}). Pick the file instead.`);
  const reader = response.body.getReader();
  /** @type {BlobPart[]} */ let parts = [];
  /** @type {Blob[]} */ const blobs = [];
  let got = 0, pending = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    parts.push(value); got += value.length; pending += value.length;
    if (got > pin.size) { await reader.cancel(); throw Error(`${pin.name} is larger than pinned.`); }
    if (pending >= 64 * MiB) { blobs.push(new Blob(parts)); parts = []; pending = 0; }
    progress(got / pin.size);
  }
  const file = new File([...blobs, new Blob(parts)], pin.name);
  if (file.size !== pin.size) throw Error(`${pin.name} download is ${file.size} bytes, pinned ${pin.size}.`);
  return file;
}

// ---- Section 1: TWRP via Odin protocol (Samsung Download Mode) ----

/** @param {Iterable<File>} files */
export function selectTwrp(files) {
  const [file, extra] = [...files];
  if (!file || extra) throw Error(`Select exactly ${s9.twrp.name}.`);
  if (!matchesPin(file, s9.twrp)) throw Error(`${file.name} is not the pinned ${s9.twrp.name} (name or size differs).`);
  return file;
}

/**
 * Writes only RECOVERY. Never reboots: a normal boot would restore the stock recovery.
 * @param {{beginSession():Promise<void>,getPitData():Promise<{findEntryByName(n:string):{partitionSize:number}|undefined}>,flashPartition(n:string,f:Blob):Promise<void>}} odin
 * @param {File} input
 * @param {{consent:boolean,confirmation:string}} consent
 * @param {(message:string,fraction:number)=>void} report
 * @param {()=>void} assertSession
 */
export async function installTwrp(odin, input, consent, report, assertSession) {
  if (!consent.consent || consent.confirmation !== TWRP_CONFIRMATION) throw Error(`Acknowledge the warning and type ${TWRP_CONFIRMATION}.`);
  const file = selectTwrp([input]);
  report(`Checking SHA-256: ${file.name}`, 0);
  const digest = await checksum(file, fraction => report(`Checking SHA-256: ${file.name}`, fraction));
  if (digest !== s9.twrp.sha256) throw Error(`SHA-256 mismatch: ${file.name}. No flashing started.`);
  assertSession();
  report('Reading partition table (PIT)', 0);
  await odin.beginSession();
  const pit = await odin.getPitData();
  for (const name of ['BOOT', 'SYSTEM', 'VENDOR', 'USERDATA']) {
    if (!pit.findEntryByName(name)) throw Error(`PIT has no ${name} partition: this does not look like a Galaxy S9. Nothing written.`);
  }
  const recovery = pit.findEntryByName(s9.twrp.partition);
  if (!recovery) throw Error('PIT has no RECOVERY partition. Nothing written.');
  if (!(recovery.partitionSize >= file.size)) throw Error('TWRP image is larger than RECOVERY. Nothing written.');
  assertSession();
  report(`Writing ${file.name} → RECOVERY`, 0);
  await odin.flashPartition(s9.twrp.partition, file);
  report('RECOVERY written. Do not reboot normally: boot straight into TWRP now (see steps).', 1);
}

// ---- Section 2: postmarketOS images from TWRP over ADB ----

/** @typedef {{run(command:string):Promise<{code:number,out:string}>, pipe(command:string,file:Blob,progress:(fraction:number)=>void):Promise<{code:number,out:string}>}} Shell */

/** Placeholder pins (size 0 / empty hash) make every entry unusable. */
export function pinsFilled() {
  return s9.images.every(image => image.size > 0 && /^[0-9a-f]{64}$/.test(image.sha256));
}

/** @param {Iterable<File>} files */
export function selectRomImages(files) {
  if (!pinsFilled()) throw Error('S9 image pins are not filled in yet (site/s9-manifest.js). Refusing to continue.');
  const selected = [...files];
  if (selected.length !== s9.images.length) throw Error(`Select exactly ${s9.images.map(i => i.name).join(', ')}.`);
  return s9.images.map(image => {
    const matches = selected.filter(file => file.name === image.name);
    if (matches.length !== 1 || matches[0].size !== image.size) {
      throw Error(`${image.name} is missing, duplicated, or has the wrong size for ${s9.release}.`);
    }
    return { ...image, file: matches[0] };
  });
}

/** @param {string} partition */
const devicePath = partition => `${s9.byName}/${partition}`;

/** Partition names come from the manifest only; this guards against shell injection anyway. */
function safePath(path) {
  if (!/^[A-Za-z0-9/._-]+$/.test(path)) throw Error(`Unsafe device path: ${path}`);
  return path;
}

/** @param {Shell} shell @param {string} command */
async function ok(shell, command) {
  const result = await shell.run(command);
  if (result.code !== 0) throw Error(`Command failed (${result.code}): ${command}`);
  return result.out.trim();
}

/** @param {Shell} shell @param {string} path */
async function blockSize(shell, path) {
  const direct = await shell.run(`blockdev --getsize64 ${safePath(path)}`);
  let size = Number(direct.out.trim());
  if (direct.code !== 0 || !/^\d+$/.test(direct.out.trim())) {
    const real = await ok(shell, `readlink -f ${safePath(path)}`);
    const sectors = await ok(shell, `cat /sys/class/block/${safePath(real).split('/').pop()}/size`);
    size = Number(sectors) * 512;
  }
  if (!Number.isSafeInteger(size) || size <= 0) throw Error(`Could not read the size of ${path}.`);
  return size;
}

/** @param {string} mounts @param {string} device */
const isMounted = (mounts, device) => mounts.split('\n').some(line => line.split(' ')[0] === device);

/** @param {Shell} shell */
export async function inspectS9(shell, { needFormatTool = false } = {}) {
  const product = await ok(shell, 'getprop ro.product.device');
  if (product !== s9.device) throw Error(`Expected ${s9.device}; phone reports ${product || 'unknown'}.`);
  if (!await ok(shell, 'getprop ro.twrp.version')) throw Error('Phone does not report TWRP (ro.twrp.version). Boot into TWRP first.');
  const mounts = await ok(shell, 'cat /proc/mounts');
  const sizes = {};
  for (const partition of [...s9.images.map(i => i.partition), s9.userdata.partition]) {
    const path = devicePath(partition);
    if ((await shell.run(`test -b ${safePath(path)}`)).code !== 0) throw Error(`${path} is not a block device.`);
    const real = await ok(shell, `readlink -f ${path}`);
    // TWRP auto-mounts USERDATA on /data and /sdcard; that is handled at the format step.
    if (partition !== s9.userdata.partition && isMounted(mounts, real)) throw Error(`${partition} (${real}) is mounted in TWRP. Unmount it first.`);
    sizes[partition] = await blockSize(shell, path);
  }
  if (needFormatTool && (await shell.run('command -v mke2fs')).code !== 0) throw Error('TWRP has no mke2fs; cannot format USERDATA.');
  return { product, sizes };
}

/**
 * @param {Shell} shell
 * @param {ReturnType<typeof selectRomImages>} images
 * @param {{consent:boolean,confirmation:string,formatUserdata:boolean,reboot:boolean}} options
 * @param {(message:string,fraction:number)=>void} report
 * @param {()=>void} assertSession
 */
export async function installRom(shell, images, options, report, assertSession) {
  if (!options.consent || options.confirmation !== ROM_CONFIRMATION) throw Error(`Acknowledge the warning and type ${ROM_CONFIRMATION}.`);
  const selected = selectRomImages(images.map(image => image.file));
  assertSession();
  const info = await inspectS9(shell, { needFormatTool: options.formatUserdata });
  for (const image of selected) {
    if (image.size > info.sizes[image.partition]) throw Error(`${image.name} is larger than ${image.partition}.`);
    report(`Checking SHA-256: ${image.name}`, 0);
    const digest = await checksum(image.file, fraction => report(`Checking SHA-256: ${image.name}`, fraction));
    if (digest !== image.sha256) throw Error(`SHA-256 mismatch: ${image.name}. No flashing started.`);
  }
  // Order: rootfs and boot partition first, kernel last. No retry, no rollback.
  const order = ['SYSTEM', 'VENDOR', 'BOOT'].map(partition => {
    const image = selected.find(i => i.partition === partition);
    if (!image) throw Error(`Manifest has no image for ${partition}.`);
    return image;
  });
  for (const image of order) {
    assertSession();
    const path = safePath(devicePath(image.partition));
    const label = `Writing ${image.name} → ${image.partition}`;
    report(label, 0);
    const result = await shell.pipe(`dd of=${path} bs=${MiB}`, image.file, fraction => report(label, fraction));
    if (result.code !== 0) throw Error(`dd to ${image.partition} failed (${result.code}): ${result.out.trim()}`);
    await ok(shell, 'sync');
    assertSession();
    report(`Verifying ${image.partition} on the phone`, 0);
    const sum = (await ok(shell, `head -c ${image.size} ${path} | sha256sum`)).split(/\s+/)[0];
    if (sum !== image.sha256) throw Error(`${image.partition} read back wrong data after writing (${sum}). Do not reboot; retry the write.`);
    report(`${image.partition} verified`, 1);
  }
  if (options.formatUserdata) {
    assertSession();
    report(`Formatting USERDATA as ext4 (${s9.userdata.label})`, 0);
    const path = safePath(devicePath(s9.userdata.partition));
    const real = await ok(shell, `readlink -f ${path}`);
    for (const mount of ['/sdcard', '/data']) await shell.run(`umount ${mount}`); // best effort, re-checked below
    if (isMounted(await ok(shell, 'cat /proc/mounts'), real)) throw Error(`USERDATA (${real}) is still mounted; unmount /data and /sdcard in TWRP and retry.`);
    await ok(shell, `mke2fs -F -t ext4 -L ${s9.userdata.label} ${path}`);
  }
  if (options.reboot) {
    assertSession();
    report('Requesting reboot', 0);
    await shell.run('reboot').catch(() => {}); // the USB link drops as the phone restarts
    report('Written, verified and reboot requested.', 1);
  } else {
    report('Written and verified. Reboot from TWRP when ready.', 1);
  }
}
