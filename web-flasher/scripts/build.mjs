import { cp, mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { build } from 'esbuild';

await rm('dist', { recursive: true, force: true });
await mkdir('dist');
await cp('site/style.css', 'dist/style.css');
await build({ entryPoints: ['site/app.js'], outfile: 'dist/app.js', bundle: true,
  format: 'esm', platform: 'browser', target: 'es2022', minify: true, legalComments: 'linked' });
// ?v=<content hash> so a redeploy is picked up despite the host's cache (GitHub Pages: max-age=600)
const version = async file => createHash('sha256').update(await readFile(`dist/${file}`)).digest('hex').slice(0, 10);
let html = await readFile('site/index.html', 'utf8');
for (const file of ['app.js', 'style.css']) html = html.replace(`"./${file}"`, `"./${file}?v=${await version(file)}"`);
assert(html.includes('app.js?v=') && html.includes('style.css?v='), 'asset links not versioned');
await writeFile('dist/index.html', html);
const notices = [];
for (const path of ['@lineageos-infra/libmjolnir/LICENSE', 'hash-wasm/LICENSE', 'hash-wasm/src/sha256.c',
  '@yume-chan/adb/LICENSE', '@yume-chan/adb-daemon-webusb/LICENSE', '@yume-chan/adb-credential-web/LICENSE',
  '@yume-chan/stream-extra/LICENSE', '@yume-chan/struct/LICENSE', '@yume-chan/async/LICENSE',
  '@yume-chan/event/LICENSE', '@yume-chan/no-data-view/LICENSE']) {
  const source = await readFile(`node_modules/${path}`, 'utf8');
  const notice = path.endsWith('LICENSE') ? source : source.match(/^(?:\s*\/\*[\s\S]*?\*\/)+/)?.[0];
  assert(notice && /[Cc]opyright/.test(notice), `Missing third-party notice: ${path}`);
  notices.push(`${path}\n${notice}`);
}
await writeFile('dist/THIRD-PARTY-NOTICES.txt', notices.join('\n\n'));
