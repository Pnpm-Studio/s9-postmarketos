import { fetchPinned, installRom, installTwrp, selectRomImages, selectTwrp, ROM_CONFIRMATION, TWRP_CONFIRMATION } from './s9.js';
import { adbShell, connectAdb, connectOdin } from './s9-usb.js';
import { s9 } from './s9-manifest.js';

/** @template {HTMLElement} T @param {string} id @returns {T} */
function el(id) {
  const node = document.getElementById(id);
  if (!node) throw Error(`Missing interface element: ${id}`);
  return /** @type {T} */ (node);
}
const message = error => error instanceof Error ? error.message : String(error);

/**
 * One flasher section: connect button, file picker, consent, flash button.
 * @param {{prefix:string, supported:boolean, connect:()=>Promise<{usb:USBDevice|undefined}&Record<string,any>>,
 *   ready:()=>boolean, run:(session:any,input:any,report:(m:string,f:number)=>void,assertSession:()=>void,consent:{consent:boolean,confirmation:string})=>Promise<void>,
 *   doneNote:string, log?:HTMLElement}} config
 */
function section({ prefix, supported, connect, ready, run, doneNote, log }) {
  const connectButton = /** @type {HTMLButtonElement} */ (el(`${prefix}-connect`));
  const flash = /** @type {HTMLButtonElement} */ (el(`${prefix}-flash`));
  const risk = /** @type {HTMLInputElement} */ (el(`${prefix}-risk`));
  const confirm = /** @type {HTMLInputElement} */ (el(`${prefix}-confirm`));
  const status = el(`${prefix}-status`);
  const progress = /** @type {HTMLProgressElement} */ (el(`${prefix}-progress`));
  const st = { session: null, usb: null, lost: false, busy: false, finished: false, input: null };

  const update = () => {
    connectButton.disabled = !supported || st.busy || st.session !== null || st.lost;
    flash.disabled = !supported || !st.session || st.lost || st.busy || st.finished || !st.input || !ready() || !risk.checked;
  };
  const report = (text, fraction = 0) => {
    status.textContent = text;
    progress.value = Math.round(Math.max(0, Math.min(1, fraction)) * 100);
    el(`${prefix}-progress-value`).textContent = `${progress.value}%`;
    if (log && log.lastElementChild?.textContent !== text) {
      const entry = document.createElement('li');
      entry.textContent = text;
      log.append(entry);
    }
  };
  const assertSession = () => {
    if (st.lost || !st.session) throw Error('USB session lost. Stop and reload the page before reconnecting; no automatic retry.');
  };
  if (!supported) report('Open this page over HTTPS (or localhost) in desktop Chrome or Edge for WebUSB.');
  else navigator.usb.addEventListener('disconnect', event => {
    if (st.usb && event.device === st.usb) {
      st.lost = true;
      if (!st.finished) report('USB disconnected. A flash may be incomplete; reload before reconnecting.');
      update();
    }
  });

  connectButton.addEventListener('click', async () => {
    st.busy = true; update();
    try {
      const connected = await connect();
      st.session = connected;
      st.usb = connected.usb ?? null;
      report('Connected. Select the file(s), confirm, and flash.');
    } catch (error) {
      st.lost = true;
      report(`${message(error)} Reload to try again.`);
    } finally { st.busy = false; update(); }
  });
  flash.addEventListener('click', async () => {
    if (flash.disabled) return;
    st.busy = true; update();
    try {
      await run(st.session, st.input, report, assertSession, { consent: risk.checked, confirmation: confirm.value });
      st.finished = true;
      report(doneNote, 1);
    } catch (error) {
      st.lost = true;
      report(`STOPPED: ${message(error)} Do not retry blindly; reload the page first.`);
    } finally { st.busy = false; update(); }
  });
  risk.addEventListener('change', update);
  confirm.addEventListener('input', update);
  return { st, update, report, setInput(value) { st.input = value; update(); } };
}

/** "Download from this site" button: fetches the pinned files next to the page, then selects them.
 * @param {string} id @param {{name:string,size:number}[]} pins @param {(m:string,f:number)=>void} report @param {(files:File[])=>void} pick */
function download(id, pins, report, pick) {
  const button = /** @type {HTMLButtonElement} */ (el(id));
  button.addEventListener('click', async () => {
    button.disabled = true;
    try {
      const files = [];
      for (const pin of pins) files.push(await fetchPinned(pin, f => report(`Downloading ${pin.name}`, f)));
      pick(files);
      report('Downloaded and selected. The SHA-256 is checked before anything is written.', 1);
    } catch (error) {
      report(message(error), 0);
      button.disabled = false;
    }
  });
}

/** Wires both S9 sections; returns the panel so the caller can show/hide it. */
export function initS9(supported) {
  // Section 1: TWRP
  const twrpFile = /** @type {HTMLInputElement} */ (el('twrp-file'));
  const twrpConfirm = /** @type {HTMLInputElement} */ (el('twrp-confirm'));
  const twrp = section({
    prefix: 'twrp', supported,
    connect: async () => {
      const odin = await connectOdin();
      return Object.assign(odin, { usb: odin.usbDevice });
    },
    ready: () => twrpConfirm.value === TWRP_CONFIRMATION,
    run: (odin, file, report, assertSession, consent) => installTwrp(odin, file, consent, report, assertSession),
    doneNote: 'TWRP written. Now hold Vol Down + Power until the screen is black, then immediately hold Vol Up + Bixby + Power until TWRP appears.'
  });
  const pickTwrp = files => {
    try {
      twrp.setInput(selectTwrp(files));
      el('twrp-picked').textContent = `${files[0].name}: name and size match`;
    } catch (error) {
      twrp.setInput(null);
      el('twrp-picked').textContent = message(error);
    }
  };
  twrpFile.addEventListener('change', () => pickTwrp([...twrpFile.files ?? []]));
  download('twrp-download', [s9.twrp], twrp.report, pickTwrp);
  twrpConfirm.addEventListener('input', twrp.update);

  // Section 2: postmarketOS images via ADB in TWRP
  const romFiles = /** @type {HTMLInputElement} */ (el('rom-files'));
  const romConfirm = /** @type {HTMLInputElement} */ (el('rom-confirm'));
  const format = /** @type {HTMLInputElement} */ (el('rom-userdata'));
  const reboot = /** @type {HTMLInputElement} */ (el('rom-reboot'));
  const rom = section({
    prefix: 'rom', supported,
    connect: async () => {
      const { adb, usb } = await connectAdb();
      return { adb, usb, shell: adbShell(adb) };
    },
    ready: () => romConfirm.value === ROM_CONFIRMATION,
    run: (session, images, report, assertSession, consent) => installRom(session.shell, images,
      { ...consent, formatUserdata: format.checked, reboot: reboot.checked }, report, assertSession),
    doneNote: 'Done. The images were verified on the phone; first boot and SSH still need checking by hand.',
    log: el('s9-log')
  });
  el('rom-info').textContent = s9.release === 'PLACEHOLDER'
    ? 'Image pins are not filled in yet: this section will refuse to flash until site/s9-manifest.js is updated.'
    : `Build ${s9.release}.`;
  const pickRom = files => {
    const list = el('rom-selected');
    try {
      const images = selectRomImages(files);
      rom.setInput(images);
      list.replaceChildren(...images.map(image => {
        const entry = document.createElement('li');
        entry.textContent = `${image.name} → ${image.partition} (${(image.size / 1024 / 1024).toFixed(1)} MiB)`;
        return entry;
      }));
    } catch (error) {
      rom.setInput(null);
      const entry = document.createElement('li');
      entry.textContent = message(error);
      list.replaceChildren(entry);
    }
  };
  romFiles.addEventListener('change', () => pickRom([...romFiles.files ?? []]));
  download('rom-download', s9.images, rom.report, pickRom);
  romConfirm.addEventListener('input', rom.update);
  return el('s9-panel');
}
