// Galaxy S9 (Exynos, SM-G960F, samsung-starlte). Single pin block: fill the PLACEHOLDER
// values with `node scripts/fill-s9-manifest.mjs <out-dir>` once the image build exists.
// Entries with size 0 or an empty sha256 make Section 2 refuse to run (fail closed).
export const s9 = {
  device: 'starlte',
  model: 'Samsung Galaxy S9 SM-G960F (Exynos)',
  // Section 1: TWRP 3.7.0 for starlte, from ~/projects/oldphones/s9/twrp/twrp.img.sha256
  twrp: {
    name: 'twrp-3.7.0_9-0-starlte.img',
    partition: 'RECOVERY',
    size: 42665984,
    sha256: '905f81903849a5b981fe8915c91d2ba025358f79324e2427c2b704a4f9e46a4e'
  },
  // Section 2: written from TWRP over ADB. `device` paths are the only write targets.
  release: 'v2026.10.15-s9',
  // CORS-enabled mirror, one folder per release: <mirror><release>/<name>. Tried when the file is not next to the page.
  mirror: 'https://huggingface.co/PhilippLinux/s9-postmarketos/resolve/main/',
  byName: '/dev/block/platform/11120000.ufs/by-name',
  images: [
    { name: 'samsung-starlte-root.img', partition: 'SYSTEM', size: 1318060032, sha256: '1bc97b90648babc544c11dfe7595db1bec032d9a8b7597127b71d082b268dc62' },
    // full-size pmOS boot partition image (512 MiB; the shrunk one was only a heimdall workaround)
    { name: 'samsung-starlte-boot.img', partition: 'VENDOR', size: 536870912, sha256: '973eef396319a3c51b691804c2b6cb9725587c0fa4542e13dd0e2a42c450d650' },
    { name: 'boot.img', partition: 'BOOT', size: 38621184, sha256: 'f07ced3496993980040fdb76f9cdf1e26ea5b10d7386af123c591d513f33e6cf' }
  ],
  userdata: { partition: 'USERDATA', label: 's9-srv' }
};
