#!/usr/bin/env python3
"""Assemble a self-contained Markdown context document from the latest data files.

Reads the refreshed CSVs, the PB Bitcoin summary, and the updated workbook,
so every number in the document comes from the files on disk rather than
being retyped. Contains client names and wallet addresses; never the API
key or client emails.

    python3 batch/build_context_doc.py
"""
import csv, json, os, datetime as dt
from openpyxl import load_workbook

HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "output")
def rd(p): return list(csv.DictReader(open(os.path.join(OUT, p))))
def money(v): return f"${float(v):,.2f}" if v not in (None, "") else "—"
def d(v):
    if isinstance(v, dt.datetime): return v.strftime("%Y-%m-%d")
    return str(v)[:10] if v else "—"

FUNDS_TAGS = {"Adamo OTC": "OTC desk", "Brute OTC": "OTC desk", "SP4-1": "Client Return", "SP4-2": "AK receive",
              "SP4-3": "FromMain", "SP4-4": "SR receive", "SP4-5": "JoeyTunes", "SP4-6": "JoeyTunes2",
              "SP4-7": "J TripleBarrel", "SP4-8": "Calvin"}

bal10 = rd("ucf10_balances.csv")
net10 = {r["wallet"]: r for r in rd("refresh10_net_funding.csv")}
pb = json.load(open(os.path.join(OUT, "pb_btc_summary.json")))
brit = sorted(rd("britany_inbounds.csv"), key=lambda r: r["datetime_utc"])
ws = load_workbook(os.path.join(OUT, "Inbound_OTC_Requests_updated.xlsx"))["Crypto Sends to PayPal"]

def sheet_rows():
    for r in range(2, 49):
        tag = ws.cell(r, 4).value
        if not tag: continue
        sends = [(ws.cell(r, a).value, ws.cell(r, a+1).value) for a in (14, 16, 18, 20) if ws.cell(r, a).value is not None]
        yield dict(row=r, tag=tag, name=ws.cell(r,1).value or "", cust=ws.cell(r,2).value or "", recip=ws.cell(r,3).value or "",
                   label=ws.cell(r,5).value or "", cur=ws.cell(r,6).value or "", addr=ws.cell(r,7).value, first=d(ws.cell(r,8).value),
                   current=ws.cell(r,9).value or 0, funded=ws.cell(r,10).value or 0, comments=ws.cell(r,12).value or "",
                   sends=sends, sent=sum(a for a, _ in sends if isinstance(a, (int, float))))
rows = list(sheet_rows())
sp4 = [x for x in rows if x["tag"].startswith("SP4")]
pbr = {x["tag"]: x for x in rows if x["tag"].startswith("PB")}

L = []
w = L.append
w("# Crypto Wallet Tracking — Full Context Handoff")
w(f"\n*Generated {dt.date.today()} from the repo's data files. Balances are snapshots dated per section; run \"Update crypto funds UCF\" for fresh numbers.*\n")
w("**Sharing note:** this document contains client names and wallet addresses (already in the operational sheet) but no API keys and no client emails.\n")

w("## 1. What this is\n")
w("""An operational tracker for an OTC / PayPal-funding workflow. Crypto (mostly PYUSD on Ethereum, some ETH and BTC) lands in a set of internally-controlled "receipt" wallets, then gets forwarded to individual clients' own wallets, from which the clients move value into PayPal. The tracking answers, per wallet: how much came in, when it first crossed $1k, what it holds now, and what was sent onward to whom.

Tooling was built over ~two weeks in the GitHub repo `pmaster/CryptoAddressBalanceQuerier` (branch `claude/crypto-wallet-debank-csv-s7znnz`):

- **`server.py` + `index.html`** — a local web GUI (paste addresses → CSV) with a tiny proxy, because the data APIs block browser CORS. Dependency-free Python.
- **`batch/inbounds.py`** — per-wallet current balance (and optionally raw inbound transfers). `--balances-only` is the fast mode (1 request/wallet).
- **`batch/net_funding.py`** — full transfer history per wallet with **on-disk caching** (`batch/cache/<address>.json`; only new transfers since the last run are fetched), swap-aware "genuine funding" totals, and the first-≥$1k date.
- **`batch/btc_pb_analyze.py`** — Bitcoin wallets via Blockstream (txs) + mempool.space (historical USD price).
- **`batch/build_paypal_sheet.py`** — refreshes the `Crypto Sends to PayPal` tab of the ops workbook from chain data (writes to a copy).
- **`batch/build_context_doc.py`** — generates this document.

Data providers: **Zerion** (free API key; EVM chains) for Ethereum wallets; **Blockstream + mempool.space** (public, no key) for Bitcoin. DeBank was ruled out (paid, ~$200 minimum). Ethereum results were spot-verified directly against the chain via public RPC (token `balanceOf` calls) — Zerion matched within pennies.
""")

w("## 2. Definitions used everywhere\n")
w("""| Term | Meaning |
|---|---|
| **Current Funds** | USD value of the wallet's holdings right now, **verified tokens only**. Zerion's own headline total is *not* used because it includes scam "airdrop" tokens with fabricated prices (one test wallet showed $800k of fake value). Totals are recomputed from per-position data. |
| **Total Funded to Wallet** | Sum of *genuine* inbound transfers ≥ $50, in USD at the time of receipt. **DEX-swap legs are excluded**: when the wallet swaps token A for token B, the incoming B is not new money. Detection: a same-wallet outbound of comparable value (±20%) within the prior 30 minutes **and** a smart contract on at least one leg. (Timing alone gave false positives on the busy OTC wallets — two unrelated peer transfers 48s apart looked like a swap. The contract test fixed that; verified against every known case.) |
| **Initial Funding Date >$1k** | Date of the first *single* genuine inbound transfer worth ≥ $1,000 (not cumulative). |
| **Send** | An outbound transfer to a plain wallet (EOA). Transfers into contracts (DEX/bridge legs) are not sends to a client. Stablecoin sends are recorded as **token amount** (995.0, not $994.84); ETH/BTC sends as **USD at the time of the send**. Timestamps are **America/New_York**, matching the workbook. |
| **Scam filtering** | Four layers: Zerion's spam classifier, the token's verified flag, fungible-only (NFT airdrops excluded), and a USD floor. Result on this data set: only USDT/USDC/PYUSD/ETH ever survive. |
| **BTC "funded"** | Pure deposits only — change outputs from the wallet's own spends are excluded (the raw explorer stat double-counts them). USD at the historical price on the deposit date. "Sender" is the input address of the deposit transaction. |
""")

w("## 3. Wallet inventory\n")
w("### 3a. The 10 \"funds\" wallets (Adamo OTC, Brute OTC, SP4-1 … SP4-8)\n")
w(f"Balances as of **2026-09-08**; net funding (swap-excluded, all-time) as of 2026-09-02.\n")
w("| Tag | Label | Address | Current | Total funded (net) | First ≥$1k |")
w("|---|---|---|---:|---:|---|")
tot = 0
for r in bal10:
    n = net10.get(r["wallet"], {}); tot += float(r["total_usd"])
    w(f"| {r['wallet']} | {FUNDS_TAGS.get(r['wallet'],'')} | `{r['address']}` | {money(r['total_usd'])} | {money(n.get('net_funding_usd'))} | {n.get('initial_funding_date_1k','—')} |")
w(f"| **Total** | | | **{money(tot)}** | | |")
w("\nAdamo OTC and Brute OTC are high-volume pass-through desks (~$2.8M and ~$3.7M lifetime net inflow, holding only ~$10k / ~$7.5k at any time). SP4-1..8 were funded once each in July 2026 and are drawn down over time; SP4-6 dropped ~$35k in a single day on 9/8.\n")

w("### 3b. SP4-9 … SP4-50 (the \"Seed Phrase 4\" series) — from the `Crypto Sends to PayPal` tab\n")
w("As of **2026-09-09**. Recipient = the client wallet this SP4 wallet forwards to. SP4-11, 18, 20 and 24–50 have never been used (zero on-chain activity).\n")
w("| Tag | Client | Custodian | Recipient wallet | Funding label | Cur | First ≥$1k | Current | Total funded | Total sent |")
w("|---|---|---|---|---|---|---|---:|---:|---:|")
for x in sp4:
    if x["tag"] in ("SP4-24",): w("| SP4-24 … SP4-50 | — | — | — | — | — | — | $0 | $0 | $0 |")
    if int(x["tag"].split("-")[1]) >= 24: continue
    w(f"| {x['tag']} | {x['name'] or '—'} | {x['cust'] or '—'} | {('`'+x['recip']+'`') if x['recip'] else '—'} | {x['label'] or '—'} | {x['cur'] or '—'} | {x['first']} | {money(x['current'])} | {money(x['funded'])} | {money(x['sent'])} |")
w("\nAddresses for SP4-9..50:\n")
for x in sp4: w(f"- {x['tag']}: `{x['addr']}`")
w("")

w("### 3c. PB Bitcoin wallets\n")
w("Numbered PB-9…PB-13 (nothing below 9 exists yet). As of **2026-09-09**; USD for deposits/sends at the historical BTC price on the day; \"holds\" at that day's price. Each has sent to exactly one on-chain destination.\n")
w("| Tag | Label | Address | Client (custodian) | Sends to | Funded | Sent | Holds |")
w("|---|---|---|---|---|---:|---:|---:|")
for tag in ("PB-9","PB-10","PB-11","PB-12","PB-13"):
    p = pb["wallets"][tag]; s = pbr.get(tag, {})
    client = f"{s.get('name')} ({s.get('cust')})" if s.get("name") else "—"
    dest = p["recipients"][0] if p["recipients"] else "—"
    w(f"| {tag} | {p['label']} | `{p['address']}` | {client} | `{dest}` | {money(p['total_funded_usd'])} ({p['total_funded_btc']:.8f} BTC) | {money(sum(x['usd'] or 0 for x in p['sends']))} | {money(p['balance_usd'])} ({p['balance_btc']:.8f} BTC) |")
w("""
Notes on the PB rows:
- **PB-11 → Britany Stoddard**: its destination is her registered BTC deposit address in the workbook's Requests tab (see §5).
- **PB-12 → Jennifer Simpson**: same logic. Custodian "Kyle" is *inferred* from her Requests-tab Quant (the two clients present in both tabs both have Quant = Custodian).
- **PB-13** is Robert Caro's pre-existing row (custodian Sahil, recipient entered by hand as his ETH wallet `0xa00d7A76…`). Its only on-chain send is a 0.001 BTC test on 9/8 to `bc1q9r2e7…`.
- **PB-10**'s destination `bc1qs6qz4sg…` and PB-13's test destination are not in the workbook — identity still open.
- **PB-9 "CG Payouts Test"** is not really a test wallet: it holds ~$21.6k. Name/custodian/recipient intentionally left blank per instruction. It shows current > funded because BTC appreciated since the May deposit.
""")
w("Per-transaction detail (NY time):\n")
for tag in ("PB-9","PB-10","PB-11","PB-12","PB-13"):
    p = pb["wallets"][tag]; w(f"**{tag}** ({p['label']})")
    for x in p["deposits"]: w(f"- IN  {x['ny']} — {x['btc']:.8f} BTC = {money(x['usd'])} @ ${x['btc_price']:,.0f} from `{x['from'][0]}`")
    for x in p["sends"]:    w(f"- OUT {x['ny']} — {x['btc']:.8f} BTC = {money(x['usd'])} @ ${x['btc_price']:,.0f} to `{x['to']}`")
    w("")

w("## 4. Outbound sends recorded per SP4 wallet (NY time)\n")
w("From the chain, as of 2026-09-09. Two entries in the ops sheet — **SP4-12 Send 2 (4,842.13)** and **SP4-14 Send 2 (4,734.42)** — have no date and are *not* on-chain; the wallets still hold far too much for them to have happened. They appear to be planned amounts entered ahead of time and were left in place.\n")
for x in sp4:
    if not x["sends"]: continue
    parts = []
    for a, t in x["sends"]:
        if isinstance(a, str): parts.append(f"[note: {a[:40]}…]")
        else: parts.append(f"{a:,.2f} on {d(t) if t else 'no date'}")
    w(f"- **{x['tag']}** ({x['name'] or 'unassigned'}, {x['cur']}): " + "; ".join(parts) + f" — total {money(x['sent'])}")
w("")

w("## 5. The ops workbook: `Inbound_OTC_Requests.xlsx`\n")
w("""Tabs: **Requests** (client intake: name, email, status, ratings, and each client's *registered* BTC / PYUSD deposit addresses), **Cluster Statuses** (per-cluster PayPal fund totals; has its own formulas), **Readme**, **Priority Queue**, and **Crypto Sends to PayPal** — the master catalog this project maintains. Readme rules: don't resize rows/columns, don't delete requests (update status instead), keep it tidy.

`Crypto Sends to PayPal` columns: A Client Name · B Custodian · C Receipt Address Type (in practice: the **recipient wallet address**) · D Tag · E Initial Funding Label · F Currency · G Source Wallet · H Initial Funding Date >$1k · I Current Funds · J Total Funded to Wallet · K Current Funds Date · L Comments · M Total Sent (`=SUM(N,P,R,T)` formula) · N/O Send 1 amount/date · P/Q Send 2 · R/S Send 3 · T/U Send 4.

**How the 9/9 refresh treated it:** computed columns (H, I, J, K, Send slots) overwritten from chain data; every human-entered field (A, B, C, E, L) preserved; a Send slot holding free text (SP4-10's "CANCEL…" note) never overwritten; Total Sent kept as the sheet's own formula. Layout: PB-9..12 in rows 45–48 (replacing a stray SP4-50 duplicate), PB-13 = Robert Caro's existing row 2 tagged in place, a stub at row 73 cleared. Other tabs verified byte-identical.

**Discrepancies found (sheet → chain), all written as chain values:** SP4-9 Send 4 5,532.32→5,519.51 · SP4-13 Send 3 2,811.21→2,811.12 · SP4-15 Sends 23/4,488/4,333→24.05/4,486.10/4,341.01 · SP4-16 Send 3 4,076→4,076.57 · SP4-19 Send 2 4,315.12→4,315.19 · SP4-21 Send 1 4,383.13→4,383.34 · SP4-22 Send 1 4,323.66→4,323.63 · SP4-23 Sends 4,831/3,232→4,821.78/3,232.22. **Zero recipient mismatches** — every column-C address matched where the chain says the money went. SP4-15's first "send" ($24 in ETH) went to a different address (`0x42ff948b…`) than Charmen Bingham's; kept because the sheet already counted it.

Spelling: the Requests tab says "Brittany Stoddard", the PayPal tab "Britany Stoddard"; the PayPal tab's spelling was kept.
""")

w("## 6. Britany Stoddard — worked example of the flow\n")
tot_eth = sum(float(r["usd_value"]) for r in brit)
p11 = pb["wallets"]["PB-11"]; tot_btc_usd = sum(x["usd"] or 0 for x in p11["sends"]); tot_btc = sum(x["btc"] for x in p11["sends"])
w(f"Two addresses, both fully swept to $0 as of 2026-09-09. Everything she received came from **four internal wallets** — no external senders.\n")
w(f"- **ETH `0x5c3E0EAa0c39E1940B4F82a53beacE055586C96C`** — {money(tot_eth)} in PYUSD across {len(brit)} transfers:")
lab = {"0x28aa29d3cb526d4d8e9492bf42ed04aff45388f5":"SP4-9","0xdb5c1f4ddc0a2d815564db5f5e72ae76ad97f363":"SP4-21","0x79c6cc78bc98bbfaf23ed93343638e2e5021fed9":"SP4-22"}
for r in brit:
    w(f"  - {r['datetime_utc'][:16]} UTC — {float(r['amount']):,.2f} PYUSD ({money(r['usd_value'])}) from {lab.get(r['sender'], r['sender'])}")
w(f"- **BTC `bc1qr6gjt789g48v99z8r920lpw77kkkcherkhq052`** — {tot_btc:.8f} BTC = {money(tot_btc_usd)} at receipt-time prices, all from PB-11:")
for x in p11["sends"]: w(f"  - {x['ny']} NY — {x['btc']:.8f} BTC ({money(x['usd'])} @ ${x['btc_price']:,.0f})")
w(f"\n**Total received: ~{money(tot_eth + tot_btc_usd)}** at time of receipt (the BTC portion is worth ~$14.8k at the 9/9 price of ~$79k).\n")

w(open(os.path.join(HERE, "RUNBOOK.md")).read())
w("")

w("## 8. Data-provider realities (why runs sometimes stall)\n")
w("""- **Zerion free tier** is advertised as 2,000 requests/day at 3 rps, but behaves like a slowly refilling token bucket: a burst succeeds, then long stretches of HTTP 429. `/positions/` (needed for verified balances) and `/portfolio` (headline total) are throttled separately; positions has been blocked for 3+ hours at a time while portfolio stayed open. Retrying into a 429 burns the same budget. Reliable recovery: the **midnight-UTC reset**.
- Mitigations built in: adaptive global pacing (gap grows on 429, shrinks on success; `ZERION_MIN_GAP` env var forces a slow start), a 20-minute starvation watchdog instead of retry caps, `--balances-only` to avoid redundant history pulls, and the transfer cache so history is fetched incrementally. First-time fetch of a busy wallet ≈ 10 s; cached re-run ≈ 2 s. Low-activity wallets were always one page, so caching doesn't speed those up.
- The cloud container restarts often; the repo (including the cache) is the durable state — always commit and push.
- Bitcoin lookups (Blockstream / mempool.space) are public, keyless, and have never rate-limited.
""")

w("## 9. Open items\n")
w("""- Identify PB-10's send destination `bc1qs6qz4sgy44s23w32ah07ms4rphshk5knxzlw67` (not in the workbook).
- Identify PB-13's 0.001 BTC test-send destination `bc1q9r2e7n8e98arvu0jkrah404xztcd462hlhq4l9`.
- Jennifer Simpson's custodian ("Kyle") is inferred, not confirmed.
- SP4-9's tag text in the original tracking sheet was truncated ("TripleBarrel …").
- SP4-1's address has only ever been confirmed from the user's typed input, not a second source.
- SP4-12 / SP4-14 planned "Send 2" amounts (not on-chain) inflate Total Sent for those rows.
- The updated workbook is delivered via chat and deliberately not committed to the repo (Requests tab carries client emails); it is gitignored.
""")

w("## 10. Repo layout\n")
w("""```
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
```""")

path = os.path.join(OUT, "CONTEXT_crypto_wallet_tracking.md")
open(path, "w").write("\n".join(L) + "\n")
print(f"wrote {path}  ({sum(1 for _ in open(path))} lines, {os.path.getsize(path):,} bytes)")
