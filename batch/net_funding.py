#!/usr/bin/env python3
"""Net external funding per wallet, with DEX swaps excluded.

A DEX swap shows up in Zerion's transaction history as an outbound
transfer (the token sold) and, moments later, an inbound transfer (the
token bought) — sometimes even tagged operation_type='receive' rather
than 'trade', so filtering by operation_type alone is not reliable.
Either way it is not new money: the wallet already owned the value
being swapped.

Proximity in time and value alone is NOT enough to call something a
swap: a busy wallet (an OTC desk, say) can send to one counterparty
and separately receive from an unrelated one within the same window
purely by coincidence, especially at higher transaction volume. The
distinguishing signal that held up under testing is whether either
counterparty is a smart contract (a DEX router, aggregator, or bridge)
rather than a plain wallet (EOA) — genuine peer-to-peer transfers run
EOA-to-EOA, while every swap/bridge mechanism observed here touched a
contract on at least one leg. So a candidate match only counts as a
swap leg if that holds too.

This script pulls each wallet's transaction history (in and out, all
operation types) and flags an inbound transfer as a swap leg when an
outbound transfer of comparable USD value from the same wallet
occurred within SWAP_WINDOW_SECONDS beforehand AND either its
recipient or the inbound's sender is a contract. Genuine external
funding is what remains.

Confirmed on-chain transfers never change, so re-fetching a wallet's
entire history on every run is pure waste once it's been seen before.
Each wallet's raw transfer list is cached in batch/cache/<address>.json
(unclassified — the swap-detection logic re-runs on the full cached
list every time, so improving that logic later doesn't require
invalidating anything). A run only asks Zerion for transfers newer
than the cached high-water mark via filter[min_mined_at], so a wallet
with 350 old transfers and zero new ones costs one cheap "anything
new?" request instead of full re-pagination. is_contract() lookups
(against the Ethereum RPC, not Zerion — doesn't touch the API quota,
but contract-vs-EOA status is permanent too) are cached the same way
in batch/cache/_contracts.json.

    ZERION_KEY=zk_... python3 batch/net_funding.py wallets.txt [--min-usd 50]

Writes batch/output/<prefix>_net_funding.csv and prints a summary.
"""

import argparse
import csv
import json
import os
import subprocess
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from inbounds import api_get, read_wallets, is_verified, OUT_DIR   # noqa: E402

MAX_PAGES = 20
SWAP_WINDOW_SECONDS = 1800     # 30 min: covers multi-tx swap routes, not unrelated deposits
SWAP_VALUE_TOLERANCE = 0.20    # 20%: covers slippage + fees on the swap leg
ETH_RPC = "https://ethereum-rpc.publicnode.com"
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
CONTRACT_CACHE_PATH = os.path.join(CACHE_DIR, "_contracts.json")
# Re-check the cached high-water mark this far back on every run: cheap insurance
# against a transfer landing out of order right at the boundary between runs.
OVERLAP_SECONDS = 300


def _load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.replace(tmp, path)   # atomic: a crash mid-write can't corrupt the cache


_contract_cache = _load_json(CONTRACT_CACHE_PATH, {})


def is_contract(address):
    """True if `address` has on-chain bytecode (a contract, not a wallet).

    Contract-vs-EOA status never changes for an already-deployed address,
    so results are cached to disk across runs.
    """
    if not address:
        return False
    address = address.lower()
    if address in _contract_cache:
        return _contract_cache[address]
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_getCode",
                          "params": [address, "latest"]})
    try:
        out = subprocess.run(["curl", "-s", "-m", "20", "-X", "POST", ETH_RPC,
                              "-H", "Content-Type: application/json", "--data", payload],
                             capture_output=True, text=True, timeout=25).stdout
        code = json.loads(out).get("result", "0x")
    except Exception:
        code = "0x"          # RPC hiccup: fail closed (treat as EOA, not a swap)
    result = len(code) > 2
    _contract_cache[address] = result
    _save_json(CONTRACT_CACHE_PATH, _contract_cache)   # small file; save every lookup, crash-safe
    return result


def parse_iso(s):
    # '2026-08-30T21:32:11Z' -> seconds since epoch, no external deps
    from datetime import datetime, timezone
    return datetime.strptime(s.split("+")[0].rstrip("Z"), "%Y-%m-%dT%H:%M:%S").replace(
        tzinfo=timezone.utc).timestamp()


def fetch_transfers_since(address, key, since_ts=None):
    """Fungible transfers (both directions) for the wallet, oldest first.

    With `since_ts` set, only transfers at or after that time are fetched
    (via filter[min_mined_at]) — the caller is expected to merge these into
    whatever it already has cached.
    """
    params = {
        "currency": "usd",
        "filter[trash]": "only_non_trash",
        "filter[asset_types]": "fungible",
        "page[size]": 100,
    }
    if since_ts is not None:
        params["filter[min_mined_at]"] = str(int(since_ts * 1000))
    path = f"wallets/{address}/transactions/"
    out = []
    for _ in range(MAX_PAGES):
        res = api_get(path, params, key)
        data = res.get("data", [])
        for tx in data:
            a = tx.get("attributes", {})
            if a.get("status") == "failed":
                continue
            ts = parse_iso(a.get("mined_at", ""))
            for tr in a.get("transfers", []):
                fung = tr.get("fungible_info") or {}
                value = tr.get("value")
                if value is None or not is_verified(fung):
                    continue
                out.append({
                    "ts": ts,
                    "date_utc": a.get("mined_at", "")[:10],
                    "direction": tr.get("direction"),
                    "operation_type": a.get("operation_type", ""),
                    "token": fung.get("symbol") or "?",
                    "usd_value": float(value),
                    "sender": (tr.get("sender") or a.get("sent_from") or "").lower(),
                    "recipient": (tr.get("recipient") or a.get("sent_to") or "").lower(),
                    "tx_hash": a.get("hash") or "",
                })
        nxt = (res.get("links") or {}).get("next")
        if not nxt or not data:
            break
        after = urllib.parse.parse_qs(urllib.parse.urlsplit(nxt).query).get("page[after]", [None])[0]
        if not after:
            break
        params["page[after]"] = after
    out.sort(key=lambda r: r["ts"])
    return out


def _transfer_key(t):
    return (t["tx_hash"], t["direction"], t["token"], round(t["usd_value"], 6))


def cache_path(address):
    return os.path.join(CACHE_DIR, f"{address.lower()}.json")


def get_transfers_cached(address, key):
    """Full transfer history for the wallet, fetching only what's new since
    the last cached run and merging it with what's already on disk."""
    cache = _load_json(cache_path(address), {"max_ts": None, "transfers": []})
    since = cache["max_ts"] - OVERLAP_SECONDS if cache["max_ts"] is not None else None
    fresh = fetch_transfers_since(address, key, since)

    seen = {_transfer_key(t) for t in cache["transfers"]}
    new_count = 0
    for t in fresh:
        k = _transfer_key(t)
        if k not in seen:
            cache["transfers"].append(t)
            seen.add(k)
            new_count += 1
    cache["transfers"].sort(key=lambda r: r["ts"])
    cache["max_ts"] = cache["transfers"][-1]["ts"] if cache["transfers"] else (since or 0)
    _save_json(cache_path(address), cache)
    return cache["transfers"], new_count


def net_funding(address, key, min_usd):
    transfers, new_count = get_transfers_cached(address, key)
    outs = [t for t in transfers if t["direction"] == "out"]

    genuine, swaps = [], []
    for t in transfers:
        if t["direction"] != "in" or t["usd_value"] < min_usd:
            continue
        candidates = [
            o for o in outs
            if o["token"] != t["token"]
            and 0 <= t["ts"] - o["ts"] <= SWAP_WINDOW_SECONDS
            and abs(o["usd_value"] - t["usd_value"]) <= SWAP_VALUE_TOLERANCE * max(o["usd_value"], t["usd_value"])
        ]
        # Timing + value proximity alone isn't enough — require a contract on
        # at least one leg, or two coincidental peer transfers get misread as a swap.
        is_swap = any(is_contract(o["recipient"]) or is_contract(t["sender"]) for o in candidates)
        (swaps if is_swap else genuine).append(t)

    return genuine, swaps, new_count


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument("wallets", nargs="?", default=os.path.join(here, "wallets_sp4_full.txt"))
    ap.add_argument("--min-usd", type=float, default=50.0)
    ap.add_argument("--prefix", default="sp4")
    args = ap.parse_args()

    key = os.environ.get("ZERION_KEY")
    if not key:
        sys.exit("ZERION_KEY env var is required")

    wallets = read_wallets(args.wallets)
    rows = []
    for label, addr in wallets:
        genuine, swaps, new_count = net_funding(addr, key, args.min_usd)
        total = round(sum(t["usd_value"] for t in genuine), 2)
        swap_total = round(sum(t["usd_value"] for t in swaps), 2)
        first_1k = min((t["date_utc"] for t in genuine if t["usd_value"] >= 1000), default="")
        cache_note = f"+{new_count} new" if new_count else "cache hit, nothing new"
        print(f"{label:8} genuine ${total:>12,.2f}  (excluded ${swap_total:>10,.2f} "
              f"across {len(swaps)} swap-leg transfer(s))  first>=$1k: {first_1k}  [{cache_note}]", flush=True)
        rows.append({"wallet": label, "address": addr,
                      "net_funding_usd": total, "swap_excluded_usd": swap_total,
                      "swap_legs_excluded": len(swaps),
                      "initial_funding_date_1k": first_1k})

    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, f"{args.prefix}_net_funding.csv")
    fields = ["wallet", "address", "net_funding_usd", "swap_excluded_usd",
              "swap_legs_excluded", "initial_funding_date_1k"]
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
