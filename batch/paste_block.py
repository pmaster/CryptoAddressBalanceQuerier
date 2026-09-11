#!/usr/bin/env python3
"""Emit a tab-separated block for columns H..U of the 'Crypto Sends to PayPal'
sheet, one row per line in the SAME order as a pasted copy of the sheet.

    python3 batch/paste_block.py <sheet_paste.tsv> [--prefix ucf42]

Input: the sheet copied as TSV (header row + data rows; column A..U layout).
Output columns (H..U): Initial Funding Date >$1k, Current Funds, Total Funded
to Wallet, Current Funds Date, Comments (passed through verbatim), Total Sent,
Send 1-4 Amount/Date.  Rules match build_paypal_sheet.py: chain data wins for
computed cells; a Send slot holding free text is kept; a sheet Send entry
beyond what the chain shows (a planned send) is kept; Comments are never
touched.  Discrepancies are printed to stderr.
"""
import csv, datetime as dt, json, os, re, sys
from zoneinfo import ZoneInfo
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_paypal_sheet import eth_sends  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "output")
NY = ZoneInfo("America/New_York"); TODAY = dt.datetime.now(NY)
prefix = sys.argv[sys.argv.index("--prefix") + 1] if "--prefix" in sys.argv else "ucf42"

def num(s):
    s = (s or "").strip().replace("$", "").replace(",", "")
    try: return float(s)
    except ValueError: return None

def fmt_amt(v): return f"{v:.2f}" if v is not None else ""
def fmt_dt(d):  return f"{d.month}/{d.day}/{d.year} {d:%H:%M:%S}"

rows = list(csv.reader(open(sys.argv[1]), delimiter="\t"))[1:]
bal = {r["wallet"]: r for r in csv.DictReader(open(os.path.join(OUT, f"{prefix}_balances.csv")))}
net = {r["wallet"]: r for r in csv.DictReader(open(os.path.join(OUT, f"{prefix}_net_funding.csv")))}
pb = json.load(open(os.path.join(OUT, "pb_btc_summary.json")))["wallets"]
notes = []

for r in rows:
    r += [""] * (21 - len(r))
    tag, addr = r[3].strip(), r[6].strip().lower()
    if not tag: continue
    if tag in pb:
        w = pb[tag]
        if w["address"] != addr: notes.append(f"{tag}: sheet address {addr} != tracked {w['address']}"); continue
        first, cur, funded = w["initial_funding_date_1k"] or "", w["balance_usd"], w["total_funded_usd"]
        sends = [(dt.datetime.strptime(s["ny"], "%Y-%m-%d %H:%M:%S"), round(s["usd"], 2)) for s in w["sends"]]
    elif tag in bal:
        if bal[tag]["address"].lower() != addr: notes.append(f"{tag}: sheet address {addr} != tracked {bal[tag]['address']}"); continue
        first, cur, funded = net[tag]["initial_funding_date_1k"], float(bal[tag]["total_usd"]), float(net[tag]["net_funding_usd"])
        sends = [(when, amt) for when, amt, _, _ in eth_sends(addr)]
    else:
        notes.append(f"{tag}: not tracked, row left as-is"); print("\t".join(r[7:21])); continue

    for col, name, chain in ((8, "Current Funds", cur), (9, "Total Funded", funded)):
        old = num(r[col])
        if old is not None and abs(old - chain) > max(1, 0.001 * chain): notes.append(f"{tag}: {name} sheet {old:,.2f} -> chain {chain:,.2f}")
    if r[7].strip() and first and r[7].strip() != first: notes.append(f"{tag}: first>$1k sheet {r[7]} -> chain {first}")

    slots = [(r[13 + 2*i], r[14 + 2*i]) for i in range(4)]
    out_slots, si = [], 0
    for when, amt in sends:
        while si < 4 and slots[si][0].strip() and num(slots[si][0]) is None:
            notes.append(f"{tag}: Send {si+1} holds a note, kept: {slots[si][0][:40]!r}"); out_slots.append(slots[si]); si += 1
        if si >= 4: notes.append(f"{tag}: more sends than slots, not written: {when:%m/%d} {amt}"); continue
        old = num(slots[si][0])
        if old is not None and abs(old - amt) > 0.01: notes.append(f"{tag}: Send {si+1} sheet {old} -> chain {amt} ({when:%m/%d %H:%M})")
        out_slots.append((fmt_amt(amt), fmt_dt(when))); si += 1
    while si < 4:
        if slots[si][0].strip(): notes.append(f"{tag}: Send {si+1} {slots[si][0]!r} not on chain, kept (planned?)")
        out_slots.append(slots[si]); si += 1
    total = sum(v for v in (num(a) for a, _ in out_slots) if v is not None)
    print("\t".join([first, fmt_amt(cur), fmt_amt(funded), f"{TODAY.month}/{TODAY.day}/{TODAY.year}", r[11], fmt_amt(total)]
                    + [x for pair in out_slots for x in pair]))

for n in notes: print("NOTE", n, file=sys.stderr)
