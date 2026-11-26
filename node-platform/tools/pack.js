// Builds the SINGLE-FILE package for phone-only deployment:
//   dist/single-file/{package.json, render.yaml, bootstrap.js}
// bootstrap.js carries every source file inside it, unpacks them next to itself on start
// (only when missing or changed), then starts the server. Its only dependency is `pg`, which
// Render installs from the root package.json BEFORE the app starts - so nothing is installed at runtime.
const fs = require('fs'), path = require('path');
const root = path.join(__dirname, '..');
const FILES = [];
(function walk(dir) {
  for (const n of fs.readdirSync(dir)) {
    const p = path.join(dir, n), rel = path.relative(root, p).split(path.sep).join('/');
    if (fs.statSync(p).isDirectory()) { if (['node_modules', 'dist', 'tools', 'test', '.git'].includes(n)) continue; walk(p); }
    else if (/^src\/|^public\//.test(rel)) FILES.push([rel, fs.readFileSync(p).toString('base64')]);
  }
})(root);
const out = path.join(root, 'dist', 'single-file');
fs.mkdirSync(out, { recursive: true });
const boot = `// PACIFIC RIM AUCTIONS v2 - SINGLE FILE. Unpacks ${FILES.length} source files beside itself, then starts the live server.
const fs = require('fs'), path = require('path');
const FILES = ${JSON.stringify(FILES)};
for (const [rel, b64] of FILES) {
  const dest = path.join(__dirname, rel), data = Buffer.from(b64, 'base64');
  let same = false; try { same = fs.readFileSync(dest).equals(data); } catch (_) {}
  if (!same) { fs.mkdirSync(path.dirname(dest), { recursive: true }); fs.writeFileSync(dest, data); }
}
console.log('Pacific Rim Auctions: ' + FILES.length + ' files in place');
require('./src/server').start().catch((e) => { console.error('STARTUP_FAILED', e.message); process.exit(1); });
`;
fs.writeFileSync(path.join(out, 'bootstrap.js'), boot);
const pkg = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8'));
pkg.scripts = { start: 'node bootstrap.js' }; delete pkg.scripts.test; delete pkg.scripts.pack; pkg.main = 'bootstrap.js';
fs.writeFileSync(path.join(out, 'package.json'), JSON.stringify(pkg, null, 2) + '\n');
fs.copyFileSync(path.join(root, 'render.yaml'), path.join(out, 'render.yaml'));
console.log('single-file build:', out, FILES.length, 'files packed,', Math.round(fs.statSync(path.join(out, 'bootstrap.js')).size / 1024) + ' KB');
