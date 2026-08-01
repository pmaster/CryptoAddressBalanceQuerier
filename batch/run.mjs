// Headless batch runner: drives the web GUI with Playwright and saves the
// Summary/Details CSVs to batch/output/. Requires the local server
// (python3 server.py) on 127.0.0.1:8787 and ZERION_KEY in the environment.
//
//   ZERION_KEY=zk_... node batch/run.mjs [path/to/addresses.txt]
//
// Playwright is resolved from the global npm root if not installed locally.
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const here = dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
let chromium;
try { ({ chromium } = require('playwright')); }
catch { ({ chromium } = await import('/opt/node22/lib/node_modules/playwright/index.mjs')); }

if (!process.env.ZERION_KEY) { console.error('ZERION_KEY env var is required'); process.exit(1); }
const addresses = readFileSync(process.argv[2] || join(here, 'addresses.txt'), 'utf8');
const outDir = join(here, 'output');
mkdirSync(outDir, { recursive: true });

const browser = await chromium.launch();
const page = await browser.newPage();
const errors = [];
page.on('pageerror', e => errors.push('pageerror: ' + e.message));

await page.goto('http://127.0.0.1:8787/');
await page.selectOption('#provider', 'zerion');
await page.fill('#key', process.env.ZERION_KEY);
// NFT value stays off: it doubles the request count and free-tier budgets are small
await page.fill('#addresses', addresses);
await page.click('#runBtn');

const t0 = Date.now();
const timer = setInterval(async () => {
  try { console.log(Math.round((Date.now() - t0) / 1000) + 's', await page.textContent('#status')); } catch {}
}, 30000);

const waitDone = () => page.waitForFunction(
  () => document.getElementById('status').textContent.startsWith('Done'), null, { timeout: 170 * 60 * 1000 });
await waitDone();

for (let round = 1; round <= 4; round++) {
  const retry = page.locator('#retryBtn');
  if (await retry.isHidden()) break;
  console.log('ROUND', round, '- retrying:', await retry.textContent());
  await retry.click();
  await waitDone();
}
clearInterval(timer);

console.log('STATUS:', await page.textContent('#status'));
console.log('GRAND:', await page.textContent('#grandTotal'), await page.textContent('#walletCount'));
console.log('ELAPSED:', Math.round((Date.now() - t0) / 1000) + 's');

writeFileSync(join(outDir, 'wallet_balances_summary.csv'), await page.inputValue('#csvOut'));
await page.click('#tabDetail');
writeFileSync(join(outDir, 'wallet_balances_details.csv'), await page.inputValue('#csvOut'));
console.log('JS_ERRORS:', errors.length ? errors : 'none');
await browser.close();
console.log('BATCH_DONE');
