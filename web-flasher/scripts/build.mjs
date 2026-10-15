import { cp, mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import assert from 'node:assert/strict';
import { build } from 'esbuild';

await rm('dist', { recursive: true, force: true });
await mkdir('dist');
await Promise.all(['index.html', 'style.css'].map(file => cp(`site/${file}`, `dist/${file}`)));
await build({ entryPoints: ['site/app.js'], outfile: 'dist/app.js', bundle: true,
  format: 'esm', platform: 'browser', target: 'es2022', minify: true, legalComments: 'linked' });
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
