# Crypto Wallet Tracking — Full Context Handoff

*Generated 2026-09-11 from the repo's data files. Balances are snapshots dated per section; run "Update crypto funds UCF" for fresh numbers.*

**Sharing note:** this document contains client names and wallet addresses (already in the operational sheet) but no API keys and no client emails.

## 1. What this is

An operational tracker for an OTC / PayPal-funding workflow. Crypto (mostly PYUSD on Ethereum, some ETH and BTC) lands in a set of internally-controlled "receipt" wallets, then gets forwarded to individual clients' own wallets, from which the clients move value into PayPal. The tracking answers, per wallet: how much came in, when it first crossed $1k, what it holds now, and what was sent onward to whom.

Tooling was built over ~two weeks in the GitHub repo `pmaster/CryptoAddressBalanceQuerier` (branch `claude/crypto-wallet-debank-csv-s7znnz`):

- **`server.py` + `index.html`** — a local web GUI (paste addresses → CSV) with a tiny proxy, because the data APIs block browser CORS. Dependency-free Python.
- **`batch/inbounds.py`** — per-wallet current balance (and optionally raw inbound transfers). `--balances-only` is the fast mode (1 request/wallet).
- **`batch/net_funding.py`** — full transfer history per wallet with **on-disk caching** (`batch/cache/<address>.json`; only new transfers since the last run are fetched), swap-aware "genuine funding" totals, and the first-≥$1k date.
- **`batch/btc_pb_analyze.py`** — Bitcoin wallets via Blockstream (txs) + mempool.space (historical USD price).
- **`batch/build_paypal_sheet.py`** — refreshes the `Crypto Sends to PayPal` tab of the ops workbook from chain data (writes to a copy).
- **`batch/build_context_doc.py`** — generates this document.

Data providers: **Zerion** (free API key; EVM chains) for Ethereum wallets; **Blockstream + mempool.space** (public, no key) for Bitcoin. DeBank was ruled out (paid, ~$200 minimum). Ethereum results were spot-verified directly against the chain via public RPC (token `balanceOf` calls) — Zerion matched within pennies.

## 2. Definitions used everywhere

| Term | Meaning |
|---|---|
| **Current Funds** | USD value of the wallet's holdings right now, **verified tokens only**. Zerion's own headline total is *not* used because it includes scam "airdrop" tokens with fabricated prices (one test wallet showed $800k of fake value). Totals are recomputed from per-position data. |
| **Total Funded to Wallet** | Sum of *genuine* inbound transfers ≥ $50, in USD at the time of receipt. **DEX-swap legs are excluded**: when the wallet swaps token A for token B, the incoming B is not new money. Detection: a same-wallet outbound of comparable value (±20%) within the prior 30 minutes **and** a smart contract on at least one leg. (Timing alone gave false positives on the busy OTC wallets — two unrelated peer transfers 48s apart looked like a swap. The contract test fixed that; verified against every known case.) |
| **Initial Funding Date >$1k** | Date of the first *single* genuine inbound transfer worth ≥ $1,000 (not cumulative). |
| **Send** | An outbound transfer to a plain wallet (EOA). Transfers into contracts (DEX/bridge legs) are not sends to a client. Stablecoin sends are recorded as **token amount** (995.0, not $994.84); ETH/BTC sends as **USD at the time of the send**. Timestamps are **America/New_York**, matching the workbook. |
| **Scam filtering** | Four layers: Zerion's spam classifier, the token's verified flag, fungible-only (NFT airdrops excluded), and a USD floor. Result on this data set: only USDT/USDC/PYUSD/ETH ever survive. |
| **BTC "funded"** | Pure deposits only — change outputs from the wallet's own spends are excluded (the raw explorer stat double-counts them). USD at the historical price on the deposit date. "Sender" is the input address of the deposit transaction. |

## 3. Wallet inventory

### 3a. The 10 "funds" wallets (Adamo OTC, Brute OTC, SP4-1 … SP4-8)

Balances as of **2026-09-08**; net funding (swap-excluded, all-time) as of 2026-09-02.

| Tag | Label | Address | Current | Total funded (net) | First ≥$1k |
|---|---|---|---:|---:|---|
| Adamo OTC | OTC desk | `0x2f58b30bd40fcb1806c2fb0b81e381a9881530bc` | $10,120.52 | $2,823,855.49 | 2025-05-19 |
| Brute OTC | OTC desk | `0x9244a6962d8f2eefdcfec223f68d83df293d9797` | $7,531.73 | $3,687,554.75 | 2026-01-04 |
| SP4-1 | Client Return | `0x13c5738200a7ca56c29e5744a3e93f52abd77d7b` | $33,889.25 | $73,946.26 | 2026-07-03 |
| SP4-2 | AK receive | `0x31a5817bab67bfeeb0038df2c2e1ede79a00930a` | $9,139.47 | $29,149.84 | 2026-07-03 |
| SP4-3 | FromMain | `0x691bdfb0c5a8dee9f75de8bc983bde51316eb489` | $1,423.75 | $1,500.32 | 2026-07-02 |
| SP4-4 | SR receive | `0x0828c3d976b837e790715913cc85dbd6237398fb` | $3,999.22 | $3,997.22 | 2026-07-08 |
| SP4-5 | JoeyTunes | `0x79b65b17af2ec4087d0957bcfae172c3c6210312` | $20,249.55 | $72,886.77 | 2026-07-08 |
| SP4-6 | JoeyTunes2 | `0x82012f9fdddaaf6a8af4ef2b83b1c6ce65debcf1` | $0.93 | $143,270.47 | 2026-07-21 |
| SP4-7 | J TripleBarrel | `0xc4a749d6983bfc2bb958cb32ef9ff9dc18ba81cf` | $11,634.67 | $11,640.71 | 2026-07-23 |
| SP4-8 | Calvin | `0xc09da08738b3b0918089163e488b02a61f382404` | $8,193.67 | $97,922.68 | 2026-07-23 |
| **Total** | | | **$106,182.76** | | |

Adamo OTC and Brute OTC are high-volume pass-through desks (~$2.8M and ~$3.7M lifetime net inflow, holding only ~$10k / ~$7.5k at any time). SP4-1..8 were funded once each in July 2026 and are drawn down over time; SP4-6 dropped ~$35k in a single day on 9/8.

### 3b. SP4-9 … SP4-50 (the "Seed Phrase 4" series) — from the `Crypto Sends to PayPal` tab

As of **2026-09-09**. Recipient = the client wallet this SP4 wallet forwards to. SP4-11, 18, 20 and 24–50 have never been used (zero on-chain activity).

| Tag | Client | Custodian | Recipient wallet | Funding label | Cur | First ≥$1k | Current | Total funded | Total sent |
|---|---|---|---|---|---|---|---:|---:|---:|
| SP4-9 | Britany Stoddard | Henry | `0x5c3E0EAa0c39E1940B4F82a53beacE055586C96C` | J TripleBarrel OTC Arb | PYUSD | 2026-08-28 | $11.47 | $15,225.99 | $15,218.84 |
| SP4-10 | Kristian Bryant | Kyle | `0x2a6a845970dA871c48615d1c03Ab8ebE1cCF19D5` | Coinbase Ronnie | PYUSD | 2026-08-31 | $18,342.14 | $18,431.99 | $100.00 |
| SP4-11 | — | — | — | — | — | — | $0.00 | $0.00 | $0.00 |
| SP4-12 | Brenda Wettstein | Eric->Bryan (Sat) | `0x200117C2B75bB745c7A1027e11126da37769592a` | Coinbase Jay | PYUSD | 2026-08-30 | $15,629.14 | $16,413.25 | $5,014.96 |
| SP4-13 | Cosina Goodman | Sahil | `0x3716F639656a89ca3dd565b590D80fd1Ef5601d5` | Coinbase Jay | PYUSD | 2026-08-30 | $64.48 | $8,292.82 | $8,153.01 |
| SP4-14 | Niajsha Blanding | TSS (Eric) | `0xA7671316D4cc45a3036D1f762DF2f1e7dd08D770` | Coinbase Jay | PYUSD | 2026-08-31 | $7,824.72 | $8,243.37 | $5,216.79 |
| SP4-15 | Charmen Bingham | Henry | `0xEd086a733454C3bc54b25DBaC5f003A0d4AE1969` | Coinbase Jay | ETH | 2026-08-31 | $1.07 | $8,891.65 | $8,851.16 |
| SP4-16 | Robert Caro | Sahil | `0xa00d7A765f79e67B1376fe4fd2634794F31E1E34` | Coinbase Ronnie | PYUSD | 2026-08-31 | $20.02 | $7,818.27 | $7,819.85 |
| SP4-17 | Linda Wallace | TSS (Meek) | `0x262d33897BB453E3FB757629369DAfBAA331CD2e` | Coinbase Ronnie | PYUSD | 2026-08-31 | $6,735.56 | $9,392.49 | $2,666.37 |
| SP4-18 | — | — | — | — | — | — | $0.00 | $0.00 | $0.00 |
| SP4-19 | Miya Dymally | Kyle | `0xF975d50142BEaAE43C06C65926c352CAd452Dc46` | Coinbase Jay | PYUSD | 2026-09-01 | $2,572.21 | $6,999.65 | $4,335.19 |
| SP4-20 | — | Eric->Bryan (Sat) | — | marked for Jay | — | — | $0.00 | $0.00 | $0.00 |
| SP4-21 | Britany Stoddard | Henry | `0x5c3E0EAa0c39E1940B4F82a53beacE055586C96C` | marked for Ronnie | PYUSD | 2026-09-03 | $3,447.32 | $7,822.19 | $4,383.34 |
| SP4-22 | Britany Stoddard | Henry | `0x5c3E0EAa0c39E1940B4F82a53beacE055586C96C` | marked for Ronnie | PYUSD | 2026-09-03 | $4,213.59 | $8,517.14 | $4,323.63 |
| SP4-23 | Cosina Goodman | Sahil | `0x3716F639656a89ca3dd565b590D80fd1Ef5601d5` | marked for Ronnie | PYUSD | 2026-09-04 | $10.90 | $8,047.30 | $8,054.00 |
| SP4-24 … SP4-50 | — | — | — | — | — | — | $0 | $0 | $0 |

Addresses for SP4-9..50:

- SP4-9: `0x28aa29d3cb526d4d8e9492bf42ed04aff45388f5`
- SP4-10: `0x2acfb4445a3936e3951802245d8820d35e51d597`
- SP4-11: `0x8647f91ed8b655593bb53edc4044caa1871bda21`
- SP4-12: `0x55b2c1c111b7cfb8863c2002b77d283269182c1d`
- SP4-13: `0x709f75210f81eb736f0abcad0041d5e0016dcc1e`
- SP4-14: `0xfb63c32b75fff61fc8f1227c2d25a23f61900ca3`
- SP4-15: `0x0c557ec72a2c99640651586ecfd04d5e55fea4d6`
- SP4-16: `0x176dc7c6f438c45a51ca7566a63cddb183b5ab27`
- SP4-17: `0xae145656410a94864773384ebfc1cc5f17862f0a`
- SP4-18: `0x2e0b9a7ae2cf4622783ca2a3df9ea62b44a7400b`
- SP4-19: `0xa55c56a3a656991fcfe66a73da2527a2b957a5ea`
- SP4-20: `0x21749f9f2111662726acfda5699783789fb5dd22`
- SP4-21: `0xdb5c1f4ddc0a2d815564db5f5e72ae76ad97f363`
- SP4-22: `0x79c6cc78bc98bbfaf23ed93343638e2e5021fed9`
- SP4-23: `0x1936d5e843d24aae8f924fec21115f5bd6d39ea4`
- SP4-24: `0x04148a083592c640b743db06e270d7fae541c7b1`
- SP4-25: `0x599d42c74e9c825d3049b4b0d89f0e132fb430ff`
- SP4-26: `0x8dcae912122cd8e1bf7404867516280ed13d08ce`
- SP4-27: `0xed831ca7db345702f01d901be65fa1fce0cf63e0`
- SP4-28: `0x01dbc3d14033145bd25cd7ac51d3aa688db296c3`
- SP4-29: `0x8b4eeb4d483d82aa8b306fd20d3669964ff0a2c1`
- SP4-30: `0xd78143a261dfbec4b3c47e39c674306253effcbc`
- SP4-31: `0x9f70c0c653e6b3faedb3742ae53a8d24f8c88576`
- SP4-32: `0x137cf6959b22864aa71eefff65ef81cc5afafa91`
- SP4-33: `0x0339ddc0db14dc33c3508a00a47ecca26584d511`
- SP4-34: `0x92eb3cdbfc134951491ad3023c38b4234f91da0b`
- SP4-35: `0xf09c70d459714513bf16a59905a51660080a2600`
- SP4-36: `0x9c591546fc18ce77b4f6369cca75c745b6878d38`
- SP4-37: `0xf7fde328525084591a6e82a94045f798f309bb74`
- SP4-38: `0x39527b27c447466a5c438c03979a0fbf209c2c57`
- SP4-39: `0xea9ef846617d0cbad0cf5a54a6cea2f4cb7ec40d`
- SP4-40: `0x91697e8a4cf216eafb0168a913c2e256aa94d604`
- SP4-41: `0x92710b80112b7e5ef10fa26914e857e02a8978a1`
- SP4-42: `0x258003c0613b2980630958e5d8adcb7b2241f111`
- SP4-43: `0xb7adb2d60e588d9fc003f48d9c4a1a074602f0b2`
- SP4-44: `0x2e49f510d76fe0daa9ec53da19844ef1ce13ed85`
- SP4-45: `0x31e7e9c1e8da3179eec0e859ca86c778d00f78ea`
- SP4-46: `0x9768a65f2e5e38c3247165d96793832ce60e31b1`
- SP4-47: `0x1ff1e23b5abaf2e680062682d452914442fea593`
- SP4-48: `0x70e733b4dfc20a7819fb0b42d8a57e495adb1f8e`
- SP4-49: `0xe922de9c9e4e0531019ca7e430e29387c3b581c4`
- SP4-50: `0x607daa4af3262c4531af263db14eaecad231846f`

### 3c. PB Bitcoin wallets

Numbered PB-9…PB-13 (nothing below 9 exists yet). As of **2026-09-09**; USD for deposits/sends at the historical BTC price on the day; "holds" at that day's price. Each has sent to exactly one on-chain destination.

| Tag | Label | Address | Client (custodian) | Sends to | Funded | Sent | Holds |
|---|---|---|---|---|---:|---:|---:|
| PB-9 | CG Payouts Test | `bc1qzvewyf7gwuwu0wju68ypt2y7lzc3502qeuvx82` | — | `bc1qfg5jved2ezsx3rx4y9542gzlneryrz7pq7589n` | $20,125.72 (0.27229123 BTC) | $5.14 | $20,987.06 (0.27221982 BTC) |
| PB-10 | BTC RCPT 6 5 26 | `bc1qtwx375elyrvl696cgeg5exz5aww2xczucwskh0` | — | `bc1qs6qz4sgy44s23w32ah07ms4rphshk5knxzlw67` | $29,929.32 (0.48528790 BTC) | $7,375.16 | $28,436.73 (0.36884829 BTC) |
| PB-11 | BTC RCPT 073126 | `bc1qh99g4ct43nqc7pr92hyj3vdceut5sngrputc47` | Britany Stoddard (Henry) | `bc1qr6gjt789g48v99z8r920lpw77kkkcherkhq052` | $17,231.60 (0.27249670 BTC) | $12,979.02 | $6,587.40 (0.08544413 BTC) |
| PB-12 | BTC RCPT 260812 | `bc1qcpzuxunccc6mu4c088ed8wmtuy44453p6hj4kp` | Jennifer Simpson (Kyle) | `bc1qx4lt0an68runkshgs4dem3nnu7rs2pqluzpamh` | $21,458.89 (0.33787677 BTC) | $15,265.98 | $9,144.32 (0.11860952 BTC) |
| PB-13 | BTC RCPT 260831 | `bc1qu8ypxwm9xvlj4kruve58v27gjk20zgzhm8td5r` | Robert Caro (Sahil) | `bc1q9r2e7n8e98arvu0jkrah404xztcd462hlhq4l9` | $8,133.07 (0.10315000 BTC) | $4,680.37 | $3,416.31 (0.04431246 BTC) |

Notes on the PB rows:
- **PB-11 → Britany Stoddard**: its destination is her registered BTC deposit address in the workbook's Requests tab (see §5).
- **PB-12 → Jennifer Simpson**: same logic. Custodian "Kyle" is *inferred* from her Requests-tab Quant (the two clients present in both tabs both have Quant = Custodian).
- **PB-13** is Robert Caro's pre-existing row (custodian Sahil, recipient entered by hand as his ETH wallet `0xa00d7A76…`). Its only on-chain send is a 0.001 BTC test on 9/8 to `bc1q9r2e7…`.
- **PB-10**'s destination `bc1qs6qz4sg…` and PB-13's test destination are not in the workbook — identity still open.
- **PB-9 "CG Payouts Test"** is not really a test wallet: it holds ~$21.6k. Name/custodian/recipient intentionally left blank per instruction. It shows current > funded because BTC appreciated since the May deposit.

Per-transaction detail (NY time):

**PB-9** (CG Payouts Test)
- IN  2026-05-29 19:35:47 — 0.00131000 BTC = $96.14 @ $73,393 from `bc1q4lly7ls46w0rjqrf6g0p8zlr55mytmz3vu4src`
- IN  2026-05-30 14:38:15 — 0.27098123 BTC = $20,029.58 @ $73,915 from `bc1qdd38095l53tkfd3k9qjgcpdjvrwxwx5kj90u5s`
- OUT 2026-05-30 00:52:27 — 0.00007000 BTC = $5.14 @ $73,444 to `bc1qfg5jved2ezsx3rx4y9542gzlneryrz7pq7589n`

**PB-10** (BTC RCPT 6 5 26)
- IN  2026-06-05 16:08:32 — 0.27460790 BTC = $16,555.56 @ $60,288 from `bc1q73y9ft2rxtatygg8vlqysurz5n3v0u66e92zdu`
- IN  2026-06-08 17:40:57 — 0.21068000 BTC = $13,373.76 @ $63,479 from `bc1qnlqdq0fh2wvlwl3k8ul7cqvdyuk4z2a05xzvl3`
- OUT 2026-07-30 14:44:12 — 0.00100000 BTC = $64.82 @ $64,818 to `bc1qs6qz4sgy44s23w32ah07ms4rphshk5knxzlw67`
- OUT 2026-07-30 23:15:04 — 0.01543257 BTC = $991.34 @ $64,237 to `bc1qs6qz4sgy44s23w32ah07ms4rphshk5knxzlw67`
- OUT 2026-07-31 14:39:00 — 0.10000000 BTC = $6,319.00 @ $63,190 to `bc1qs6qz4sgy44s23w32ah07ms4rphshk5knxzlw67`

**PB-11** (BTC RCPT 073126)
- IN  2026-08-02 14:30:58 — 0.27249670 BTC = $17,231.60 @ $63,236 from `bc1qg52nfjt33pynklyeaf29mv953sqphh38zhnc3h`
- OUT 2026-08-06 14:32:21 — 0.01546000 BTC = $998.17 @ $64,565 to `bc1qr6gjt789g48v99z8r920lpw77kkkcherkhq052`
- OUT 2026-08-07 09:46:47 — 0.11215413 BTC = $7,316.49 @ $65,236 to `bc1qr6gjt789g48v99z8r920lpw77kkkcherkhq052`
- OUT 2026-09-08 18:04:03 — 0.05943000 BTC = $4,664.36 @ $78,485 to `bc1qr6gjt789g48v99z8r920lpw77kkkcherkhq052`

**PB-12** (BTC RCPT 260812)
- IN  2026-08-12 21:07:54 — 0.33787677 BTC = $21,458.89 @ $63,511 from `bc1q8n8zqexa07n3e4nvqlfp9j7lg6erk38wk0esym`
- OUT 2026-08-14 13:42:40 — 0.02000000 BTC = $1,261.42 @ $63,071 to `bc1qx4lt0an68runkshgs4dem3nnu7rs2pqluzpamh`
- OUT 2026-08-19 13:11:16 — 0.11313500 BTC = $7,746.58 @ $68,472 to `bc1qx4lt0an68runkshgs4dem3nnu7rs2pqluzpamh`
- OUT 2026-08-20 19:09:57 — 0.08612100 BTC = $6,257.98 @ $72,665 to `bc1qx4lt0an68runkshgs4dem3nnu7rs2pqluzpamh`

**PB-13** (BTC RCPT 260831)
- IN  2026-08-31 17:55:56 — 0.10315000 BTC = $8,133.07 @ $78,847 from `bc1qm8y3c04e67u6e3utm2gx2sqjq09quejpdfm9y8`
- OUT 2026-09-08 16:56:03 — 0.00100000 BTC = $78.44 @ $78,435 to `bc1q9r2e7n8e98arvu0jkrah404xztcd462hlhq4l9`
- OUT 2026-09-09 09:59:31 — 0.05782630 BTC = $4,601.93 @ $79,582 to `bc1q9r2e7n8e98arvu0jkrah404xztcd462hlhq4l9`

## 4. Outbound sends recorded per SP4 wallet (NY time)

From the chain, as of 2026-09-09. Two entries in the ops sheet — **SP4-12 Send 2 (4,842.13)** and **SP4-14 Send 2 (4,734.42)** — have no date and are *not* on-chain; the wallets still hold far too much for them to have happened. They appear to be planned amounts entered ahead of time and were left in place.

- **SP4-9** (Britany Stoddard, PYUSD): 995.00 on 2026-08-28; 3,812.21 on 2026-08-29; 4,892.12 on 2026-09-01; 5,519.51 on 2026-09-03 — total $15,218.84
- **SP4-10** (Kristian Bryant, PYUSD): 100.00 on 2026-09-01; [note: CANCEL. Kristian received too much alrea…] — total $100.00
- **SP4-12** (Brenda Wettstein, PYUSD): 172.83 on 2026-09-01; 4,842.13 on no date — total $5,014.96
- **SP4-13** (Cosina Goodman, PYUSD): 489.37 on 2026-09-01; 4,852.52 on 2026-09-02; 2,811.12 on 2026-09-03 — total $8,153.01
- **SP4-14** (Niajsha Blanding, PYUSD): 482.37 on 2026-09-02; 4,734.42 on no date — total $5,216.79
- **SP4-15** (Charmen Bingham, ETH): 24.05 on 2026-09-02; 4,486.10 on 2026-09-05; 4,341.01 on 2026-09-05 — total $8,851.16
- **SP4-16** (Robert Caro, PYUSD): 10.00 on 2026-09-02; 3,733.28 on 2026-09-04; 4,076.57 on 2026-09-07 — total $7,819.85
- **SP4-17** (Linda Wallace, PYUSD): 50.00 on 2026-09-02; 2,616.37 on 2026-09-03 — total $2,666.37
- **SP4-19** (Miya Dymally, PYUSD): 20.00 on 2026-09-02; 4,315.19 on 2026-09-04 — total $4,335.19
- **SP4-21** (Britany Stoddard, PYUSD): 4,383.34 on 2026-09-06 — total $4,383.34
- **SP4-22** (Britany Stoddard, PYUSD): 4,323.63 on 2026-09-07 — total $4,323.63
- **SP4-23** (Cosina Goodman, PYUSD): 4,821.78 on 2026-09-07; 3,232.22 on 2026-09-08 — total $8,054.00

## 5. The ops workbook: `Inbound_OTC_Requests.xlsx`

Tabs: **Requests** (client intake: name, email, status, ratings, and each client's *registered* BTC / PYUSD deposit addresses), **Cluster Statuses** (per-cluster PayPal fund totals; has its own formulas), **Readme**, **Priority Queue**, and **Crypto Sends to PayPal** — the master catalog this project maintains. Readme rules: don't resize rows/columns, don't delete requests (update status instead), keep it tidy.

`Crypto Sends to PayPal` columns: A Client Name · B Custodian · C Receipt Address Type (in practice: the **recipient wallet address**) · D Tag · E Initial Funding Label · F Currency · G Source Wallet · H Initial Funding Date >$1k · I Current Funds · J Total Funded to Wallet · K Current Funds Date · L Comments · M Total Sent (`=SUM(N,P,R,T)` formula) · N/O Send 1 amount/date · P/Q Send 2 · R/S Send 3 · T/U Send 4.

**How the 9/9 refresh treated it:** computed columns (H, I, J, K, Send slots) overwritten from chain data; every human-entered field (A, B, C, E, L) preserved; a Send slot holding free text (SP4-10's "CANCEL…" note) never overwritten; Total Sent kept as the sheet's own formula. Layout: PB-9..12 in rows 45–48 (replacing a stray SP4-50 duplicate), PB-13 = Robert Caro's existing row 2 tagged in place, a stub at row 73 cleared. Other tabs verified byte-identical.

**Discrepancies found (sheet → chain), all written as chain values:** SP4-9 Send 4 5,532.32→5,519.51 · SP4-13 Send 3 2,811.21→2,811.12 · SP4-15 Sends 23/4,488/4,333→24.05/4,486.10/4,341.01 · SP4-16 Send 3 4,076→4,076.57 · SP4-19 Send 2 4,315.12→4,315.19 · SP4-21 Send 1 4,383.13→4,383.34 · SP4-22 Send 1 4,323.66→4,323.63 · SP4-23 Sends 4,831/3,232→4,821.78/3,232.22. **Zero recipient mismatches** — every column-C address matched where the chain says the money went. SP4-15's first "send" ($24 in ETH) went to a different address (`0x42ff948b…`) than Charmen Bingham's; kept because the sheet already counted it.

Spelling: the Requests tab says "Brittany Stoddard", the PayPal tab "Britany Stoddard"; the PayPal tab's spelling was kept.

## 6. Britany Stoddard — worked example of the flow

Two addresses, both fully swept to $0 as of 2026-09-09. Everything she received came from **four internal wallets** — no external senders.

- **ETH `0x5c3E0EAa0c39E1940B4F82a53beacE055586C96C`** — $23,925.11 in PYUSD across 6 transfers:
  - 2026-08-28 18:32 UTC — 995.00 PYUSD ($994.84) from SP4-9
  - 2026-08-29 23:44 UTC — 3,812.21 PYUSD ($3,812.18) from SP4-9
  - 2026-09-01 22:43 UTC — 4,892.12 PYUSD ($4,889.64) from SP4-9
  - 2026-09-04 01:41 UTC — 5,519.51 PYUSD ($5,522.12) from SP4-9
  - 2026-09-06 21:36 UTC — 4,383.34 PYUSD ($4,383.27) from SP4-21
  - 2026-09-07 16:32 UTC — 4,323.63 PYUSD ($4,323.06) from SP4-22
- **BTC `bc1qr6gjt789g48v99z8r920lpw77kkkcherkhq052`** — 0.18704413 BTC = $12,979.02 at receipt-time prices, all from PB-11:
  - 2026-08-06 14:32:21 NY — 0.01546000 BTC ($998.17 @ $64,565)
  - 2026-08-07 09:46:47 NY — 0.11215413 BTC ($7,316.49 @ $65,236)
  - 2026-09-08 18:04:03 NY — 0.05943000 BTC ($4,664.36 @ $78,485)

**Total received: ~$36,904.13** at time of receipt (the BTC portion is worth ~$14.8k at the 9/9 price of ~$79k).

## 7. How to run everything (runbook)

### 7.1 One-time setup

- **Requirements:** Python 3.9+ (uses `zoneinfo`), `git`, `curl`. Only one pip package, and only for the workbook/document steps: `pip install openpyxl`. Everything else is standard library.
- **Zerion API key (free, no payment, no KYC):** sign up at developers.zerion.io → dashboard → create key (`zk_…`). This is the only credential. Bitcoin lookups need no key at all.
- **Clone:**
  ```
  git clone -b claude/crypto-wallet-debank-csv-s7znnz https://github.com/pmaster/CryptoAddressBalanceQuerier.git
  cd CryptoAddressBalanceQuerier
  ```
- The transfer cache (`batch/cache/`) ships with the repo, so a fresh clone already knows the history of every wallet tracked so far.

### 7.2 Every session

```
python3 server.py --port 8787 &          # local proxy; keep it running
export ZERION_KEY=zk_...                 # your key

# quota probe — 200 = go, 429 = throttled (see §8). Probe /positions/ specifically:
curl -s -o /dev/null -w '%{http_code}\n' -H "X-Access-Key: $ZERION_KEY" \
  'http://127.0.0.1:8787/api/zerion/wallets/0x28aa29d3cb526d4d8e9492bf42ed04aff45388f5/positions/?currency=usd&filter[positions]=no_filter&filter[trash]=only_non_trash&sort=-value'
```

Why the proxy: browsers and some tooling can't call these APIs directly (CORS), and the proxy allow-lists exactly the endpoints the scripts use. Your key goes to the proxy per request (`X-Access-Key` header) and is never stored. **If you pull new code, restart the server** — a stale server process answers `403 endpoint not allowed` for endpoints added later.

The GUI is optional: open http://127.0.0.1:8787, choose Zerion, paste the key and addresses, and it produces the same per-wallet CSVs interactively (with a demo mode that needs no key).

### 7.3 Wallet list files (`batch/wallets_*.txt`)

One wallet per line, `label,address`; lines starting with `#` are ignored; addresses are case-insensitive.

| File | Contents |
|---|---|
| `wallets_refresh10.txt` | The 10 "funds" wallets: Adamo OTC, Brute OTC, SP4-1 … SP4-8 |
| `wallets_sp4_9_50.txt` | SP4-9 … SP4-50 (42 wallets) |
| `wallets_sp4_9_25.txt` | SP4-9 … SP4-25 (the active subset) |
| `wallets_sp4_full.txt` | SP4-1 … SP4-23 (minus SP4-11) |
| `wallets_pb.txt` | PB-9 … PB-21 Bitcoin wallets (`tag,address[,label]`), read by `btc_pb_analyze.py` |
| `wallets_britany.txt` | Britany Stoddard's ETH address only |
| `addresses.txt` | The original 68-address sample from the very first run |

Before adding any address: it must be `0x` + exactly 40 hex characters (or a `bc1q…` Bitcoin address), pasted as text — never transcribed from a screenshot. A one-character slip silently queries a different wallet. If it's supposedly already known, diff it against the existing list first.

### 7.4 Commands

| Script | What it does | Run | Output | ~Time |
|---|---|---|---|---|
| `batch/inbounds.py` | Current balance per wallet (verified tokens only). Without `--balances-only` it also pulls raw inbound transfers ≥ `--min-usd` (default 50) — rarely needed now; `net_funding.py` supersedes it for funding totals. | `python3 batch/inbounds.py LIST --prefix P --balances-only` | `batch/output/P_balances.csv` (+ `P_inbounds.csv` without the flag) | ~1 s/wallet |
| `batch/net_funding.py` | Full transfer history (cached, incremental) → swap-excluded **Total Funded**, **Initial Funding Date >$1k**, swap legs excluded. Console shows `[+N new]` or `[cache hit, nothing new]` per wallet. | `python3 batch/net_funding.py LIST --prefix P` | `batch/output/P_net_funding.csv`; updates `batch/cache/` | ~2 s/wallet cached; ~10 s first time for a busy wallet |
| `batch/last_tx.py` | Most recent transfer over `--min-usd` (default 100) per wallet, either direction, with counterparty. | `python3 batch/last_tx.py LIST --prefix P` | `batch/output/P_last_tx.csv` | ~2 s/wallet |
| `batch/btc_address_report.py` | Any Bitcoin address: every deposit (with source address and USD at that day's price), every send (with destination), balance, totals by sender/recipient. The "how much and from whom" query. | `python3 batch/btc_address_report.py bc1q…` | console | ~10 s |
| `batch/btc_pb_analyze.py` | The PB Bitcoin wallets (list at the top of the file): deposits/sends/balances with historical USD, NY times. | `python3 batch/btc_pb_analyze.py` | `batch/output/pb_btc_summary.json` (+ raw txs in `batch/output/btc_txs/`) | ~20 s |
| `batch/build_paypal_sheet.py` | Refresh the workbook's `Crypto Sends to PayPal` tab from chain data, into a copy. Needs fresh `ucf42_balances.csv` + `ucf42_net_funding.csv` (that prefix is hard-wired) and `pb_btc_summary.json`. Row placement and PB client names are configured at the top of the script (`PB_ROWS`, `PB_CLIENT`, `STALE_ROWS`). Prints every sheet-vs-chain discrepancy. | `python3 batch/build_paypal_sheet.py SOURCE.xlsx batch/output/pb_btc_summary.json` | `batch/output/Inbound_OTC_Requests_updated.xlsx` (gitignored) | ~15 s |
| `batch/paste_block.py` | Copy-paste refresh for the Google Sheet version of the `Crypto Sends to PayPal` tab: feed it the sheet copied as TSV (all columns A..U, header included, any row order) and it prints columns H..U for every row in the same order — chain values for the computed cells, Comments passed through, free-text/planned Send entries kept. Discrepancies go to stderr. | `python3 batch/paste_block.py sheet.tsv > block.tsv` | stdout (paste at column H) | instant |
| `batch/build_context_doc.py` | Regenerates this document from the files above. | `python3 batch/build_context_doc.py` | `batch/output/CONTEXT_crypto_wallet_tracking.md` | instant |
| `batch/build_workbook.py` | Older helper: two-tab Balances/Inbounds `.xlsx` from a prefix's CSVs. | `python3 batch/build_workbook.py --prefix P` | `batch/output/P_wallets.xlsx` | instant |

Environment knobs: `ZERION_KEY` (required); `ZERION_MIN_GAP=20` makes every script start with a 20-second gap between requests (use after a throttled day instead of firing fast and backing off reactively).

### 7.5 Standard sequences

**A. "Update crypto funds UCF"** (the recurring refresh)
```
python3 batch/inbounds.py batch/wallets_refresh10.txt --prefix ucf10 --balances-only     # 1) 10 funds wallets → sum column total_usd
python3 batch/inbounds.py batch/wallets_sp4_9_50.txt  --prefix ucf42 --balances-only     # 2a) SP4-9..50 balances
python3 batch/net_funding.py batch/wallets_sp4_9_50.txt --prefix ucf42                   # 2b) SP4-9..50 funding
```
Then emit the paste block — one row per wallet SP4-9…SP4-50 in order, tab-separated, no labels: `initial_funding_date_1k` · `total_usd` · `net_funding_usd` (joined from the two CSVs on `wallet`). Blank date + 0 + 0 means never funded.

**B. Full workbook refresh** (after A's step 2)
```
python3 batch/btc_pb_analyze.py                       # PB wallets come from batch/wallets_pb.txt
python3 batch/build_paypal_sheet.py /path/to/Inbound_OTC_Requests.xlsx batch/output/pb_btc_summary.json
```
Read the printed FLAGS before sharing the file. The source workbook is never modified.

If the sheet lives in Google Sheets instead: copy the whole tab, save it as `sheet.tsv`, run `python3 batch/paste_block.py sheet.tsv`, and paste the output at column H of the first data row. Read the NOTE lines it prints (they list every sheet-vs-chain difference and any Send entry that is not on chain).

**C. "How much has X received, and from whom?"**
- Ethereum: put the address in a one-line list file, then `python3 batch/inbounds.py that.txt --prefix x --min-usd 0` and read `batch/output/x_inbounds.csv` (columns `sender`, `token`, `amount`, `usd_value`, `datetime_utc`). Group by `sender`. Label senders by looking them up in the wallet lists.
- Bitcoin: `python3 batch/btc_address_report.py bc1q…`.

**D. Adding wallets**
- New SP4/ETH wallet: append `label,address` to the relevant list; the first `net_funding.py` run fetches its full history and caches it. If it's a new client row in the workbook, add the row by hand once (tag + address); the builder then keeps it updated.
- New PB/BTC wallet: append `tag,address[,label]` to `batch/wallets_pb.txt` **and** (for the xlsx builder only) add it to `PB_ROWS` (row number) / `PB_CLIENT` (name, custodian — or omit to leave blank) in `build_paypal_sheet.py`. Identify the client by matching the wallet's send destination against the Requests tab's registered deposit addresses.

**E. Regenerate this document:** `python3 batch/build_context_doc.py` after any of the above.

**F. Commit after every run** — the cache and outputs are the durable state:
```
git add batch/cache batch/output/*.csv batch/output/*.json && git commit -m "UCF refresh" && git push
```

### 7.6 Reading the outputs

- `*_balances.csv`: `wallet, address, total_usd, wallet_tokens_usd, defi_usd, chain_count, chain_breakdown, top_holdings, top_defi` (+ `inbound_count, inbound_total_usd, external_receive_usd, history_truncated` when not `--balances-only`).
- `*_net_funding.csv`: `wallet, address, net_funding_usd, swap_excluded_usd, swap_legs_excluded, initial_funding_date_1k`. `swap_excluded_usd` > 0 means the wallet swapped tokens; those legs were not counted as funding.
- `*_inbounds.csv`: one row per inbound transfer — `wallet, address, datetime_utc, date_utc, operation_type, external_receive, internal_transfer, chain, token, token_name, amount, price_usd, usd_value, sender, sender_label, tx_hash`. `internal_transfer=TRUE` = sender is another wallet in the same list.
- `pb_btc_summary.json`: per PB tag → `balance_btc/usd, total_funded_btc/usd, initial_funding_date_1k, deposits[], sends[], recipients[]`; each deposit/send has `ny` time, `btc`, `usd`, `btc_price`, `from`/`to`, `txid`.
- `batch/cache/<address>.json`: raw transfers both directions (`ts, direction, operation_type, token, amount, usd_value, sender, recipient, tx_hash`) plus `max_ts`. Delete a file to force a full refetch.

### 7.7 Troubleshooting

| Symptom | Meaning / fix |
|---|---|
| `RuntimeError: rate limited for 900s — quota exhausted` | Zerion has throttled the key for 15+ minutes straight. Don't retry in a loop — it spends the same budget. Wait for the midnight-UTC reset (or an hour or two), then rerun; start with `ZERION_MIN_GAP=20`. |
| Probe returns 200 but the run dies immediately | Burst capacity was one request deep. Same remedy. `/portfolio` can be open while `/positions/` is blocked; always probe positions. |
| `HTTP 202` in logs | Zerion is indexing a wallet it has never seen; the script waits (up to ~3 min) automatically. |
| `Connection refused` on 127.0.0.1:8787 | Server not running — start it (§7.2). |
| `403 endpoint not allowed` | Old server process from before a code pull. Kill it and start again. |
| A balance looks too high | Check it isn't Zerion's raw total: the scripts already use verified-only positions. Spot-check on-chain with a public RPC `balanceOf` if in doubt. |
| A funding total looks too high | Look at `swap_excluded_usd`/console: a DEX swap may have been counted. The detector requires a contract on one leg; a genuine peer transfer is never excluded. |
| Numbers differ from the ops sheet | The builder prints each discrepancy. Sheet entries are sometimes rounded or entered before the transaction lands (planned sends have no date). |
| Cloud session restarted | Only the local server dies. `git pull` and restart it; nothing else is lost. |


## 8. Data-provider realities (why runs sometimes stall)

- **Zerion free tier** is advertised as 2,000 requests/day at 3 rps, but behaves like a slowly refilling token bucket: a burst succeeds, then long stretches of HTTP 429. `/positions/` (needed for verified balances) and `/portfolio` (headline total) are throttled separately; positions has been blocked for 3+ hours at a time while portfolio stayed open. Retrying into a 429 burns the same budget. Reliable recovery: the **midnight-UTC reset**.
- Mitigations built in: adaptive global pacing (gap grows on 429, shrinks on success; `ZERION_MIN_GAP` env var forces a slow start), a 20-minute starvation watchdog instead of retry caps, `--balances-only` to avoid redundant history pulls, and the transfer cache so history is fetched incrementally. First-time fetch of a busy wallet ≈ 10 s; cached re-run ≈ 2 s. Low-activity wallets were always one page, so caching doesn't speed those up.
- The cloud container restarts often; the repo (including the cache) is the durable state — always commit and push.
- Bitcoin lookups (Blockstream / mempool.space) are public, keyless, and have never rate-limited.

## 9. Open items

- Identify PB-10's send destination `bc1qs6qz4sgy44s23w32ah07ms4rphshk5knxzlw67` (not in the workbook).
- Identify PB-13's 0.001 BTC test-send destination `bc1q9r2e7n8e98arvu0jkrah404xztcd462hlhq4l9`.
- Jennifer Simpson's custodian ("Kyle") is inferred, not confirmed.
- SP4-9's tag text in the original tracking sheet was truncated ("TripleBarrel …").
- SP4-1's address has only ever been confirmed from the user's typed input, not a second source.
- SP4-12 / SP4-14 planned "Send 2" amounts (not on-chain) inflate Total Sent for those rows.
- The updated workbook is delivered via chat and deliberately not committed to the repo (Requests tab carries client emails); it is gitignored.

## 10. Repo layout

```
server.py, index.html          local GUI + API proxy (Zerion / DeBank)
batch/inbounds.py              balances (+ raw inbounds); --balances-only for speed
batch/net_funding.py           cached history, swap-aware net funding, first ≥$1k date
batch/btc_pb_analyze.py        Bitcoin PB wallets (Blockstream + historical price)
batch/build_paypal_sheet.py    refresh the workbook's Crypto Sends to PayPal tab (to a copy)
batch/build_context_doc.py     this document
batch/last_tx.py               last significant transaction per wallet
batch/wallets_*.txt            label,address lists (refresh10 = the 10 funds wallets; sp4_9_50; sp4_9_25; britany; …)
batch/cache/                   per-address transfer history + contract/EOA lookups (committed)
batch/output/                  CSV/JSON outputs; ucf10_* / ucf42_* / ucf925_* are the UCF snapshots
batch/PROCESSES.md             the UCF process definition
```
