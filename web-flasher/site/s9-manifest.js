// Galaxy S9 (SM-G960F, starlte) and S9+ (SM-G965F, star2lte), Exynos. One pin block per model: fill it with
// `node scripts/fill-s9-manifest.mjs <out-dir> <model> [release]` once the image build exists.
// Entries with size 0 or an empty sha256 make Section 2 refuse to run (fail closed).
export const models = {
  starlte: {
    label: 'Galaxy S9 · SM-G960F',
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
      { name: 'samsung-starlte-root.img', partition: 'SYSTEM', size: 1321205760, sha256: 'a35a9c20f1bd4dd8d112094f23982721989edac51d283adaa226ad48ccfd3f5b' },
      // full-size pmOS boot partition image (512 MiB; the shrunk one was only a heimdall workaround)
      { name: 'samsung-starlte-boot.img', partition: 'VENDOR', size: 536870912, sha256: '39a67316e9da031a75e3a3484b066fbc4c4801e1ab1a4c0b2aab7feb45f2ca0e' },
      { name: 'boot.img', partition: 'BOOT', size: 38752256, sha256: '088bb1f099be371c245154aa4651c46866b3f44ed24318371c1b7239d885d637' }
    ],
    userdata: { partition: 'USERDATA', label: 's9-srv' }
  },
  // Untested on hardware: same build as the S9 with the star2lte kernel config/DTB and TWRP.
  star2lte: {
    label: 'Galaxy S9+ · SM-G965F (untested)',
    device: 'star2lte',
    model: 'Samsung Galaxy S9+ SM-G965F (Exynos)',
    twrp: {
      name: 'twrp-3.7.0_9-0-star2lte.img',
      partition: 'RECOVERY',
      size: 42670080,
      sha256: 'f674dab0134f3c929982077b6a3a8de7df209a45c76ead80bc009381bcd835e1'
    },
    release: 'v2026.10.15-s9plus',
    mirror: 'https://huggingface.co/PhilippLinux/s9-postmarketos/resolve/main/',
    byName: '/dev/block/platform/11120000.ufs/by-name',
    images: [
      { name: 'samsung-star2lte-root.img', partition: 'SYSTEM', size: 1318060032, sha256: '52be430de46e5478543c0a73368b122e6df19d35f3d3268df56a2c3614f4e3a3' },
      { name: 'samsung-star2lte-boot.img', partition: 'VENDOR', size: 536870912, sha256: 'ba70491a69b330ded787cc3a0a08424bfb39fca2b476e379e5012f883a27fe5b' },
      { name: 'boot.img', partition: 'BOOT', size: 38756352, sha256: 'e8eb714114300eb5de1c67f58c51a5eef7262394773f1abe37931f4b16fb61b7' }
    ],
    userdata: { partition: 'USERDATA', label: 's9-srv' }
  }
};

/** The active model; every check reads it at call time. */
export const s9 = { ...models.starlte };

/** @param {string|null} key unknown keys keep the S9 */
export function useModel(key) {
  if (key && Object.hasOwn(models, key)) Object.assign(s9, models[key]);
  return s9;
}
