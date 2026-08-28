#!/usr/bin/env python3
"""Last significant transfer (>= threshold USD) for each labelled wallet.

Walks each wallet's transaction history newest-first and reports the first
transfer clearing the threshold, in either direction, with its counterparty.

    ZERION_KEY=zk_... python3 batch/last_tx.py [wallets.txt] [--min-usd 100]
"""

import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from inbounds import api_get, read_wallets, is_verified, OUT_DIR   # noqa: E402

MAX_PAGES = 10


def last_significant(address, key, min_usd, known):
    params = {
        "currency": "usd",
        "filter[trash]": "only_non_trash",
        "filter[asset_types]": "fungible",
        "page[size]": 100,
    }
    scanned = 0
    for _ in range(MAX_PAGES):
        res = api_get(f"wallets/{address}/transactions/", params, key)
        data = res.get("data", [])
        for tx in data:                       # newest first
            a = tx.get("attributes", {})
            scanned += 1
            if a.get("status") == "failed":
                continue
            chain = (((tx.get("relationships") or {}).get("chain") or {}).get("data") or {}).get("id", "")
            for tr in a.get("transfers", []):
                value = tr.get("value")
                if value is None or float(value) < min_usd:
                    continue
                fung = tr.get("fungible_info") or {}
                if not is_verified(fung):
                    continue
                direction = tr.get("direction")
                if direction == "in":
                    party = (tr.get("sender") or a.get("sent_from") or "").lower()
                    role = "from"
                else:
                    party = (tr.get("recipient") or a.get("sent_to") or "").lower()
                    role = "to"
                return {
                    "datetime_utc": a.get("mined_at", "").replace("T", " ").split("+")[0].rstrip("Z"),
                    "direction": {"in": "IN", "out": "OUT", "self": "SELF"}.get(direction, direction),
                    "operation_type": a.get("operation_type", ""),
                    "token": fung.get("symbol") or "?",
                    "amount": round(float((tr.get("quantity") or {}).get("float") or 0), 6),
                    "usd_value": round(float(value), 2),
                    "counterparty_role": role,
                    "counterparty": party,
                    "counterparty_label": known.get(party, ""),
                    "chain": chain,
                    "tx_hash": a.get("hash") or "",
                    "txs_scanned": scanned,
                }
        nxt = (res.get("links") or {}).get("next")
        if not nxt or not data:
            break
        import urllib.parse
        after = urllib.parse.parse_qs(urllib.parse.urlsplit(nxt).query).get("page[after]", [None])[0]
        if not after:
            break
        params["page[after]"] = after
    return None


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument("wallets", nargs="?", default=os.path.join(here, "wallets_sp4.txt"))
    ap.add_argument("--min-usd", type=float, default=100.0)
    ap.add_argument("--prefix", default="sp4")
    args = ap.parse_args()

    key = os.environ.get("ZERION_KEY")
    if not key:
        sys.exit("ZERION_KEY env var is required")

    wallets = read_wallets(args.wallets)
    known = {addr: label for label, addr in wallets}
    rows = []
    for label, addr in wallets:
        hit = last_significant(addr, key, args.min_usd, known)
        if hit:
            print(f"{label:11} {hit['datetime_utc']:19} {hit['direction']:4} "
                  f"${hit['usd_value']:>12,.2f} {hit['token']:6} {hit['counterparty_role']:4} "
                  f"{hit['counterparty']}{'  (' + hit['counterparty_label'] + ')' if hit['counterparty_label'] else ''}",
                  flush=True)
            rows.append({"wallet": label, "address": addr, **hit})
        else:
            print(f"{label:11} — no transfer >= ${args.min_usd:,.0f} found", flush=True)
            rows.append({"wallet": label, "address": addr, "datetime_utc": "",
                         "direction": "", "operation_type": "", "token": "",
                         "amount": "", "usd_value": "", "counterparty_role": "",
                         "counterparty": "", "counterparty_label": "", "chain": "",
                         "tx_hash": "", "txs_scanned": ""})

    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, f"{args.prefix}_last_tx.csv")
    fields = ["wallet", "address", "datetime_utc", "direction", "operation_type",
              "token", "amount", "usd_value", "counterparty_role", "counterparty",
              "counterparty_label", "chain", "tx_hash", "txs_scanned"]
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
