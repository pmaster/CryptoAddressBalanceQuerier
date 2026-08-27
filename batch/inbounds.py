#!/usr/bin/env python3
"""Labelled balances + significant inbound transfers, as Google-Sheets-ready CSVs.

Reads a "label,address" list, and for each wallet pulls from Zerion (via the
local proxy in server.py):

  * current positions  -> per-wallet balance summary
  * transaction history -> every inbound transfer worth >= MIN_USD that
    isn't a scam token

Scam filtering is three-layered: Zerion's own spam flag (filter[trash]),
the token's verified flag, and the USD threshold (junk airdrops have no
real price, so they cannot clear it).

Usage:
    ZERION_KEY=zk_... python3 batch/inbounds.py [wallets.txt] [--min-usd 50]

Outputs into batch/output/:
    sp4_balances.csv   one row per wallet
    sp4_inbounds.csv   one row per inbound transfer
"""

import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict

PROXY = "http://127.0.0.1:8787/api/zerion/"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "output")
MAX_PAGES = 20          # 100 transactions per page
PAGE_SIZE = 100

# Adaptive pacing: Zerion's free tier behaves like a slowly refilling bucket,
# so widen the gap on every 429 and ease it back down on success.
pace = {"gap": 0.4, "min": 0.25, "max": 60.0}
_next_slot = [0.0]


def _throttle():
    now = time.monotonic()
    slot = max(now, _next_slot[0])
    _next_slot[0] = slot + pace["gap"]
    if slot > now:
        time.sleep(slot - now)


def api_get(path, params, key, deadline=900):
    url = PROXY + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    started = time.monotonic()
    while True:
        _throttle()
        req = urllib.request.Request(url, headers={"X-Access-Key": key})
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                if resp.status == 202:          # wallet still being indexed
                    time.sleep(8)
                    continue
                pace["gap"] = max(pace["min"], pace["gap"] * 0.9)
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                pace["gap"] = min(pace["max"], pace["gap"] * 1.8)
                if time.monotonic() - started > deadline:
                    raise RuntimeError("rate limited for %ds — quota exhausted" % deadline)
                continue
            if e.code >= 500:
                time.sleep(5)
                continue
            raise
        except urllib.error.URLError:
            time.sleep(5)
            if time.monotonic() - started > deadline:
                raise


def read_wallets(path):
    out = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            label, addr = line.split(",", 1)
            out.append((label.strip(), addr.strip().lower()))
    return out


def is_verified(fungible):
    return ((fungible or {}).get("flags") or {}).get("verified") is not False


def fetch_balance(address, key):
    """Verified-only positions -> totals, per-chain split, top holdings."""
    res = api_get(f"wallets/{address}/positions/", {
        "currency": "usd",
        "filter[positions]": "no_filter",
        "filter[trash]": "only_non_trash",
        "sort": "-value",
    }, key)

    wallet_usd = defi_usd = 0.0
    by_chain = defaultdict(float)
    holdings, defi = [], []
    for p in res.get("data", []):
        a = p.get("attributes", {})
        fung = a.get("fungible_info") or {}
        if not is_verified(fung):
            continue
        chain = (((p.get("relationships") or {}).get("chain") or {}).get("data") or {}).get("id", "")
        value = float(a.get("value") or 0)
        symbol = fung.get("symbol") or a.get("name") or "?"
        qty = float(((a.get("quantity") or {}).get("float")) or 0)
        if a.get("position_type") == "wallet":
            wallet_usd += value
            holdings.append((symbol, qty, value, chain))
        else:
            signed = -value if a.get("position_type") == "loan" else value
            defi_usd += signed
            value = signed
            defi.append((a.get("protocol") or "unknown", a.get("position_type") or "", value, chain))
        by_chain[chain] += value

    holdings.sort(key=lambda r: -r[2])
    defi.sort(key=lambda r: -abs(r[2]))
    chains = sorted(((c, v) for c, v in by_chain.items() if v > 0.01), key=lambda r: -r[1])
    return {
        "total_usd": round(wallet_usd + defi_usd, 2),
        "wallet_tokens_usd": round(wallet_usd, 2),
        "defi_usd": round(defi_usd, 2),
        "chain_count": len(chains),
        "chain_breakdown": " | ".join(f"{c}:{v:,.2f}" for c, v in chains),
        "top_holdings": "; ".join(f"{s} {q:,.4f} (${v:,.2f}) [{c}]" for s, q, v, c in holdings[:10]),
        "top_defi": "; ".join(f"{p} {k} (${v:,.2f}) [{c}]" for p, k, v, c in defi[:10]),
    }


def fetch_inbounds(address, key, min_usd, known=None):
    """Every inbound transfer >= min_usd that clears the scam filters.

    `known` maps address -> label so transfers between the tracked wallets
    are identifiable rather than showing as bare hex.
    """
    known = known or {}
    rows = []
    params = {
        "currency": "usd",
        "filter[trash]": "only_non_trash",     # Zerion's own spam classifier
        "filter[asset_types]": "fungible",     # NFT "airdrops" are near-universally junk
        "page[size]": PAGE_SIZE,
    }
    path = f"wallets/{address}/transactions/"
    truncated = False
    for page in range(MAX_PAGES):
        res = api_get(path, params, key)
        data = res.get("data", [])
        for tx in data:
            a = tx.get("attributes", {})
            if a.get("status") == "failed":
                continue
            chain = (((tx.get("relationships") or {}).get("chain") or {}).get("data") or {}).get("id", "")
            op = a.get("operation_type", "")
            for tr in a.get("transfers", []):
                if tr.get("direction") != "in":
                    continue
                fung = tr.get("fungible_info") or {}
                value = tr.get("value")
                if value is None or float(value) < min_usd:   # kills priceless junk
                    continue
                if not is_verified(fung):
                    continue
                mined = a.get("mined_at", "")
                sender = (tr.get("sender") or a.get("sent_from") or "").lower()
                rows.append({
                    "sender_label": known.get(sender, ""),
                    "internal_transfer": "TRUE" if sender in known else "FALSE",
                    "datetime_utc": mined.replace("T", " ").replace("Z", "").split("+")[0],
                    "date_utc": mined[:10],
                    "operation_type": op,
                    "external_receive": "TRUE" if op == "receive" else "FALSE",
                    "chain": chain,
                    "token": fung.get("symbol") or "?",
                    "token_name": fung.get("name") or "",
                    "amount": round(float((tr.get("quantity") or {}).get("float") or 0), 8),
                    "price_usd": round(float(tr.get("price") or 0), 6),
                    "usd_value": round(float(value), 2),
                    "sender": sender,
                    "tx_hash": a.get("hash") or "",
                })
        nxt = (res.get("links") or {}).get("next")
        if not nxt or not data:
            break
        after = urllib.parse.parse_qs(urllib.parse.urlsplit(nxt).query).get("page[after]", [None])[0]
        if not after:
            break
        params["page[after]"] = after
        if page == MAX_PAGES - 1:
            truncated = True
    rows.sort(key=lambda r: r["datetime_utc"], reverse=True)
    return rows, truncated


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("wallets", nargs="?", default=os.path.join(HERE, "wallets_sp4.txt"))
    ap.add_argument("--min-usd", type=float, default=50.0)
    ap.add_argument("--prefix", default="sp4")
    ap.add_argument("--balances-only", action="store_true",
                    help="skip transaction history — 1 request per wallet instead of many")
    args = ap.parse_args()

    key = os.environ.get("ZERION_KEY")
    if not key:
        sys.exit("ZERION_KEY env var is required")

    os.makedirs(OUT_DIR, exist_ok=True)
    wallets = read_wallets(args.wallets)
    known = {addr: label for label, addr in wallets}
    bal_rows, in_rows = [], []

    for label, addr in wallets:
        print(f"[{label}] {addr}", flush=True)
        bal = fetch_balance(addr, key)
        if args.balances_only:
            inbound, truncated = [], False
            print(f"    balance ${bal['total_usd']:,.2f}", flush=True)
        else:
            inbound, truncated = fetch_inbounds(addr, key, args.min_usd, known)
        total_in = sum(r["usd_value"] for r in inbound)
        ext_in = sum(r["usd_value"] for r in inbound if r["external_receive"] == "TRUE")
        if not args.balances_only:
            print(f"    balance ${bal['total_usd']:,.2f} | inbounds {len(inbound)} "
                  f"(${total_in:,.2f}, external ${ext_in:,.2f})"
                  + ("  [TRUNCATED]" if truncated else ""), flush=True)

        row = {"wallet": label, "address": addr, **bal}
        if not args.balances_only:      # otherwise these would all read as zero
            row.update({
                "inbound_count": len(inbound),
                "inbound_total_usd": round(total_in, 2),
                "external_receive_usd": round(ext_in, 2),
                "history_truncated": "TRUE" if truncated else "FALSE",
            })
        bal_rows.append(row)
        for r in inbound:
            in_rows.append({"wallet": label, "address": addr, **r})

    bal_path = os.path.join(OUT_DIR, f"{args.prefix}_balances.csv")
    with open(bal_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(bal_rows[0].keys()))
        w.writeheader()
        w.writerows(bal_rows)

    print(f"\nwrote {bal_path} ({len(bal_rows)} wallets)")
    print(f"total balances: ${sum(r['total_usd'] for r in bal_rows):,.2f}")

    if args.balances_only:      # leave any existing inbounds export untouched
        return

    in_path = os.path.join(OUT_DIR, f"{args.prefix}_inbounds.csv")
    fields = ["wallet", "address", "datetime_utc", "date_utc", "operation_type",
              "external_receive", "internal_transfer", "chain", "token", "token_name",
              "amount", "price_usd", "usd_value", "sender", "sender_label", "tx_hash"]
    with open(in_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(in_rows)

    print(f"wrote {in_path} ({len(in_rows)} inbound transfers)")
    print(f"total inbounds: ${sum(r['usd_value'] for r in in_rows):,.2f}")


if __name__ == "__main__":
    main()
