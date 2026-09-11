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
