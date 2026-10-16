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
    release: 'v2026.10.16-s9',
    // CORS-enabled mirror, one folder per release: <mirror><release>/<name>. Tried when the file is not next to the page.
    mirror: 'https://huggingface.co/PhilippLinux/s9-postmarketos/resolve/main/',
    byName: '/dev/block/platform/11120000.ufs/by-name',
    images: [
      { name: 'samsung-starlte-root.img', partition: 'SYSTEM', size: 1322254336, sha256: '94e7a21f8043115971d28b62bc91b9769ff435e93aa860631936c560d6e70da2' },
      // full-size pmOS boot partition image (512 MiB; the shrunk one was only a heimdall workaround)
      { name: 'samsung-starlte-boot.img', partition: 'VENDOR', size: 536870912, sha256: 'c27db3f87a7b83ade6dc372d51030ef242a3bffd28205a949fbe92bc073bd50d' },
      { name: 'boot.img', partition: 'BOOT', size: 38752256, sha256: 'cded0cee6c8ea60c3260e18c39a6fa9799bad5610a7509b0e83e464897d329f3' }
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
    release: 'v2026.10.16-s9plus',
    mirror: 'https://huggingface.co/PhilippLinux/s9-postmarketos/resolve/main/',
    byName: '/dev/block/platform/11120000.ufs/by-name',
    images: [
      { name: 'samsung-star2lte-root.img', partition: 'SYSTEM', size: 1319108608, sha256: 'efbf3b0710bd9eab12bcc8336fcf9918df8cc17926bcb570443e5d6320ff65ce' },
      { name: 'samsung-star2lte-boot.img', partition: 'VENDOR', size: 536870912, sha256: 'a9e77d80928f69b21fa97719a5031050a712e796bb31f8276fed30b53a8638b0' },
      { name: 'boot.img', partition: 'BOOT', size: 38756352, sha256: 'e5d45313ef8ceb966c7175cdcaddcb1e9ff40057db4c29ce3d9c98890bceda0f' }
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
