"""PB Bitcoin wallets: deposits, sends, balances with USD at the historical price.

Fetches each wallet's transactions from Blockstream (public, keyless), prices
from mempool.space, and writes batch/output/pb_btc_summary.json. Edit the PB
list below to add wallets. Times are America/New_York to match the workbook.

    python3 batch/btc_pb_analyze.py
"""
import json, os, subprocess, datetime
from zoneinfo import ZoneInfo
NY = ZoneInfo("America/New_York")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
TX_DIR = os.path.join(OUT, "btc_txs")
os.makedirs(TX_DIR, exist_ok=True)
PB = [("PB-9","CG Payouts Test","bc1qzvewyf7gwuwu0wju68ypt2y7lzc3502qeuvx82"),
      ("PB-10","BTC RCPT 6 5 26","bc1qtwx375elyrvl696cgeg5exz5aww2xczucwskh0"),
      ("PB-11","BTC RCPT 073126","bc1qh99g4ct43nqc7pr92hyj3vdceut5sngrputc47"),
      ("PB-12","BTC RCPT 260812","bc1qcpzuxunccc6mu4c088ed8wmtuy44453p6hj4kp"),
      ("PB-13","BTC RCPT 260831","bc1qu8ypxwm9xvlj4kruve58v27gjk20zgzhm8td5r")]
_pc = {}
def price_at(ts):
    if ts in _pc: return _pc[ts]
    out = subprocess.run(["curl","-s","-m","20",f"https://mempool.space/api/v1/historical-price?currency=USD&timestamp={ts}"],capture_output=True,text=True).stdout
    try: p = json.loads(out)["prices"][0]["USD"]
    except Exception: p = None
    _pc[ts] = p; return p
now_price = json.loads(subprocess.run(["curl","-s","-m","20","https://mempool.space/api/v1/prices"],capture_output=True,text=True).stdout)["USD"]
result = {"btc_price_now": now_price, "wallets": {}}
for tag, label, addr in PB:
    txs = json.loads(subprocess.run(["curl","-s","-m","30",f"https://blockstream.info/api/address/{addr}/txs"],capture_output=True,text=True).stdout)
    json.dump(txs, open(os.path.join(TX_DIR, f"{addr}.json"), "w"))   # raw copy, for reference
    txs.sort(key=lambda t: t["status"].get("block_time", 0))
    deposits, sends = [], []
    for tx in txs:
        ts = tx["status"].get("block_time"); 
        if not ts: continue
        in_vin = any(i.get("prevout",{}).get("scriptpubkey_address")==addr for i in tx["vin"])
        to_me = sum(o["value"] for o in tx["vout"] if o.get("scriptpubkey_address")==addr)
        p = price_at(ts)
        when = datetime.datetime.fromtimestamp(ts, datetime.timezone.utc)
        rec = {"utc": when.isoformat(), "ny": when.astimezone(NY).strftime("%Y-%m-%d %H:%M:%S"), "btc_price": p, "txid": tx["txid"]}
        if not in_vin and to_me:
            srcs = sorted({i["prevout"]["scriptpubkey_address"] for i in tx["vin"] if i.get("prevout")})
            deposits.append({**rec, "btc": to_me/1e8, "usd": round(to_me/1e8*p,2) if p else None, "from": srcs})
        elif in_vin:
            for o in tx["vout"]:
                oa = o.get("scriptpubkey_address")
                if oa and oa != addr:
                    sends.append({**rec, "btc": o["value"]/1e8, "usd": round(o["value"]/1e8*p,2) if p else None, "to": oa})
    stats = json.loads(subprocess.run(["curl","-s","-m","20",f"https://blockstream.info/api/address/{addr}"],capture_output=True,text=True).stdout)["chain_stats"]
    bal_btc = (stats["funded_txo_sum"]-stats["spent_txo_sum"])/1e8
    first_1k = next((d["ny"][:10] for d in deposits if d["usd"] and d["usd"]>=1000), None)
    result["wallets"][tag] = {"label": label, "address": addr, "balance_btc": bal_btc, "balance_usd": round(bal_btc*now_price,2),
        "total_funded_usd": round(sum(d["usd"] or 0 for d in deposits),2), "total_funded_btc": sum(d["btc"] for d in deposits),
        "initial_funding_date_1k": first_1k, "deposits": deposits, "sends": sends,
        "recipients": sorted({s["to"] for s in sends})}
json.dump(result, open(os.path.join(OUT, "pb_btc_summary.json"), "w"), indent=1)
print("wrote", os.path.join(OUT, "pb_btc_summary.json"))
for tag, w in result["wallets"].items():
    print(f"\n{tag} {w['label']}  bal {w['balance_btc']:.8f} BTC = ${w['balance_usd']:,.2f}   funded ${w['total_funded_usd']:,.2f} ({w['total_funded_btc']:.8f} BTC)  first>=$1k {w['initial_funding_date_1k']}")
    for d in w["deposits"]: print(f"   IN  {d['ny']}  {d['btc']:.8f} BTC  ${d['usd']:>10,.2f} @${d['btc_price']:,.0f}  from {d['from'][0][:20]}{'...' if len(d['from'])>1 else ''}")
    for s in w["sends"]:    print(f"   OUT {s['ny']}  {s['btc']:.8f} BTC  ${s['usd']:>10,.2f} @${s['btc_price']:,.0f}  to {s['to']}")
