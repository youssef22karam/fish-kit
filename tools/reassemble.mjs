// Reassemble generated files from their split parts (each part <= 30,000 bytes).
// Usage: node tools/reassemble.mjs — rewrites fish-kit.js and
// making/scripts/fishgen/fishgen.py byte-exact from parts/, verifying SHA-256.
import { readFileSync, writeFileSync, readdirSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const TARGETS = [
  { partsDir: 'parts', out: 'fish-kit.js', sha: 'fd7ca6dae01c84832e8e80b0b95f44321044ed0f9f519be7c091a5e80086820a' },
  { partsDir: 'making/scripts/fishgen/parts', out: 'making/scripts/fishgen/fishgen.py', sha: '70e61aed45e2d0992d4dfa70a375ce69f36ebc718d1df28d8f93d2f8c7e59dd7' },
];
for (const t of TARGETS) {
  const dir = resolve(root, t.partsDir);
  const files = readdirSync(dir).filter(f => f.includes('.part')).sort();
  if (!files.length) throw new Error('no parts in ' + t.partsDir);
  const buf = Buffer.concat(files.map(f => readFileSync(resolve(dir, f))));
  const sha = createHash('sha256').update(buf).digest('hex');
  if (sha !== t.sha) throw new Error(`${t.out}: SHA mismatch ${sha} != ${t.sha}`);
  writeFileSync(resolve(root, t.out), buf);
  console.log(`reassemble: ${files.length} parts -> ${t.out} (${buf.length} bytes, SHA-256 OK)`);
}
