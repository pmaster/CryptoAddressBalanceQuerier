#!/usr/bin/env python3
"""How much has a Bitcoin address received, from whom, and where did it go.

Pure deposits only (change from the wallet's own spends is excluded), USD at
the historical BTC price on each date, times in America/New_York. Uses the
public Blockstream and mempool.space APIs — no key needed.

    python3 batch/btc_address_report.py bc1q...
"""
import datetime as dt
import json
import subprocess
import sys
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")


def get(url):
    out = subprocess.run(["curl", "-s", "-m", "30", url], capture_output=True, text=True).stdout
    return json.loads(out)


def main():
    addr = sys.argv[1].strip()
    txs = sorted(get(f"https://blockstream.info/api/address/{addr}/txs"),
                 key=lambda t: t["status"].get("block_time", 0))
    stats = get(f"https://blockstream.info/api/address/{addr}")["chain_stats"]
    now_px = get("https://mempool.space/api/v1/prices")["USD"]
    bal = (stats["funded_txo_sum"] - stats["spent_txo_sum"]) / 1e8
    print(f"{addr}\n  {len(txs)} transactions, balance {bal:.8f} BTC = ${bal*now_px:,.2f} (BTC now ${now_px:,})\n")

    in_btc = in_usd = out_btc = out_usd = 0.0
    senders, recipients = {}, {}
    for tx in txs:
        ts = tx["status"].get("block_time")
        if not ts:
            continue
        px = get(f"https://mempool.space/api/v1/historical-price?currency=USD&timestamp={ts}")["prices"][0]["USD"]
        when = dt.datetime.fromtimestamp(ts, dt.timezone.utc).astimezone(NY).strftime("%Y-%m-%d %H:%M NY")
        mine_in_vin = any(i.get("prevout", {}).get("scriptpubkey_address") == addr for i in tx["vin"])
        if not mine_in_vin:
            recv = sum(o["value"] for o in tx["vout"] if o.get("scriptpubkey_address") == addr) / 1e8
            if not recv:
                continue
            srcs = sorted({i["prevout"]["scriptpubkey_address"] for i in tx["vin"] if i.get("prevout")})
            in_btc += recv; in_usd += recv * px
            for s in srcs:
                senders[s] = senders.get(s, 0) + recv * px / len(srcs)
            print(f"  IN  {when}  {recv:.8f} BTC  ${recv*px:>10,.2f} @${px:,.0f}  from {', '.join(srcs)}")
        else:
            # This address may be co-spent with other inputs (one wallet sweeping many
            # addresses). Attribute only this address's share of the inputs to it.
            own_in = sum(i["prevout"]["value"] for i in tx["vin"]
                         if i.get("prevout", {}).get("scriptpubkey_address") == addr) / 1e8
            all_in = sum(i["prevout"]["value"] for i in tx["vin"] if i.get("prevout")) / 1e8
            change = sum(o["value"] for o in tx["vout"] if o.get("scriptpubkey_address") == addr) / 1e8
            share = own_in / all_in if all_in else 1.0
            others = len({i["prevout"]["scriptpubkey_address"] for i in tx["vin"] if i.get("prevout")}) - 1
            out_btc += own_in - change; out_usd += (own_in - change) * px
            for o in tx["vout"]:
                oa = o.get("scriptpubkey_address")
                if oa and oa != addr:
                    v = o["value"] / 1e8 * share
                    recipients[oa] = recipients.get(oa, 0) + v * px
                    note = f"  (this address's {share:.0%} share; co-spent with {others} other input address(es))" if others else ""
                    print(f"  OUT {when}  {v:.8f} BTC  ${v*px:>10,.2f} @${px:,.0f}  to {oa}{note}")

    print(f"\n  RECEIVED {in_btc:.8f} BTC = ${in_usd:,.2f} at receipt-time prices (${in_btc*now_px:,.2f} today) "
          f"from {len(senders)} sender(s)")
    for s, v in sorted(senders.items(), key=lambda x: -x[1]):
        print(f"    {s}  ~${v:,.2f}")
    print(f"  SENT     {out_btc:.8f} BTC = ${out_usd:,.2f} to {len(recipients)} recipient(s)")
    for r, v in sorted(recipients.items(), key=lambda x: -x[1]):
        print(f"    {r}  ${v:,.2f}")


if __name__ == "__main__":
    main()
