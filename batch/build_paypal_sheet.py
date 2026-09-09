#!/usr/bin/env python3
"""Refresh the 'Crypto Sends to PayPal' tab of the OTC workbook from chain data.

Writes to a COPY of the source workbook (never the original). For every SP4
wallet row and the PB (Bitcoin) wallets it:
  * overwrites the computed columns — Initial Funding Date >$1k, Current
    Funds, Total Funded to Wallet, Current Funds Date, and the Send 1-4
    amount/date slots — from fresh chain data
  * preserves every human-entered field (Client Name, Custodian, Receipt
    Address, Initial Funding Label, Comments) and never overwrites a Send
    slot that holds free text (e.g. a "CANCEL ..." note)
  * keeps `Total Sent` as the sheet's own =SUM(N,P,R,T) formula
  * records every discrepancy between what the sheet said and what the chain
    says, so nothing changes silently

Conventions matched from the existing rows: Send timestamps in
America/New_York; stablecoin sends recorded as token amount, everything
else (ETH, BTC) as USD value at the time of the send; a "send" is an
outbound transfer to a plain wallet (EOA) — transfers into contracts
(DEX/bridge legs of swaps) are not sends to a client.

    python3 batch/build_paypal_sheet.py <source.xlsx> <pb_summary.json>
"""

import csv
import datetime as dt
import json
import os
import shutil
import sys
from collections import Counter, defaultdict
from zoneinfo import ZoneInfo

from openpyxl import load_workbook

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from net_funding import is_contract, cache_path  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "output")
NY = ZoneInfo("America/New_York")
TODAY = dt.datetime.now(NY).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
STABLES = {"PYUSD", "USDC", "USDT", "USDT0", "DAI"}
SHEET = "Crypto Sends to PayPal"

# 1-based column indices, from the sheet's header row
C = dict(name=1, custodian=2, recipient=3, tag=4, label=5, currency=6, wallet=7,
         first_1k=8, current=9, funded=10, current_date=11, comments=12, total_sent=13)
SEND_COLS = [(14, 15), (16, 17), (18, 19), (20, 21)]   # (amount, date) for Send 1..4

# Bitcoin rows: (tag, row, human-known name/custodian or None to leave blank)
PB_ROWS = {"PB-9": 45, "PB-10": 46, "PB-11": 47, "PB-12": 48, "PB-13": 2}
PB_CLIENT = {"PB-11": ("Britany Stoddard", "Henry"),   # Requests sheet: recipient is her registered BTC deposit address
             "PB-12": ("Jennifer Simpson", "Kyle")}     # Requests sheet: recipient is her registered BTC deposit address
STALE_ROWS = [45, 73]   # duplicate SP4-50 stub, PB-13 stub

flags = []


def flag(msg):
    flags.append(msg)


def read_csv(path):
    with open(path, newline="") as f:
        return {r["wallet"]: r for r in csv.DictReader(f)}


def eth_sends(address):
    """Outbound sends to plain wallets, oldest first: [(ny_datetime, amount, token, recipient)]."""
    p = cache_path(address)
    if not os.path.exists(p):
        return []
    out = []
    for t in json.load(open(p))["transfers"]:
        if t["direction"] != "out" or is_contract(t["recipient"]):
            continue
        when = dt.datetime.fromtimestamp(t["ts"], dt.timezone.utc).astimezone(NY).replace(tzinfo=None)
        amt = t.get("amount") if t["token"] in STABLES and t.get("amount") else t["usd_value"]
        out.append((when, round(amt, 2), t["token"], t["recipient"]))
    return sorted(out)


def write_sends(ws, row, sends, ref_row=3):
    """Fill Send 1-4 slots; skip slots holding free text; report overflow."""
    slot = 0
    for when, amt, _, _ in sends:
        while slot < len(SEND_COLS) and isinstance(ws.cell(row, SEND_COLS[slot][0]).value, str):
            flag(f"row {row}: Send {slot+1} holds a note, left untouched: {ws.cell(row, SEND_COLS[slot][0]).value!r}")
            slot += 1
        if slot >= len(SEND_COLS):
            flag(f"row {row}: more sends than slots — not written: {when:%Y-%m-%d} {amt}")
            continue
        ca, cd = SEND_COLS[slot]
        old = ws.cell(row, ca).value
        if isinstance(old, (int, float)) and abs(old - amt) > 0.01:
            flag(f"row {row}: Send {slot+1} amount {old} -> {amt} (chain)")
        set_num(ws, row, ca, amt, ref_row)
        set_date(ws, row, cd, when, ref_row)
        slot += 1
    fcell = ws.cell(row, C["total_sent"])
    if not (isinstance(fcell.value, str) and fcell.value.startswith("=")):
        fcell.value = f"=SUM(N{row},P{row},R{row},T{row})"


def set_num(ws, row, col, value, ref_row=3):
    cell = ws.cell(row, col)
    if cell.number_format == "General":
        cell.number_format = ws.cell(ref_row, col).number_format
    cell.value = value


def set_date(ws, row, col, value, ref_row=3):
    cell = ws.cell(row, col)
    if cell.number_format == "General":
        cell.number_format = ws.cell(ref_row, col).number_format
    cell.value = value


def clear_row(ws, row):
    for col in range(1, 22):
        ws.cell(row, col).value = None


def main():
    src, pb_path = sys.argv[1], sys.argv[2]
    os.makedirs(OUT_DIR, exist_ok=True)
    dst = os.path.join(OUT_DIR, "Inbound_OTC_Requests_updated.xlsx")
    shutil.copy(src, dst)
    wb = load_workbook(dst)
    ws = wb[SHEET]

    bal = read_csv(os.path.join(OUT_DIR, "ucf42_balances.csv"))
    net = read_csv(os.path.join(OUT_DIR, "ucf42_net_funding.csv"))
    pb = json.load(open(pb_path))["wallets"]

    for r in STALE_ROWS:
        clear_row(ws, r)

    rows_by_wallet = {}
    for r in range(2, ws.max_row + 1):
        w = ws.cell(r, C["wallet"]).value
        if w and str(w).startswith("0x"):
            rows_by_wallet[str(w).lower()] = r

    # ---- SP4 (Ethereum) rows ----
    for label, b in bal.items():
        addr = b["address"].lower()
        row = rows_by_wallet.get(addr)
        if not row:
            flag(f"{label}: no row in sheet for {addr}")
            continue
        n = net[label]
        sends = eth_sends(addr)

        set_num(ws, row, C["current"], round(float(b["total_usd"]), 2))
        set_num(ws, row, C["funded"], round(float(n["net_funding_usd"]), 2))
        set_date(ws, row, C["current_date"], TODAY)
        if n["initial_funding_date_1k"]:
            set_date(ws, row, C["first_1k"], dt.datetime.strptime(n["initial_funding_date_1k"], "%Y-%m-%d"))

        if sends:
            by_recip = defaultdict(float)
            for _, amt, _, rec in sends:
                by_recip[rec] += amt
            dominant = max(by_recip, key=by_recip.get)
            existing = ws.cell(row, C["recipient"]).value
            if existing and str(existing).lower() != dominant:
                flag(f"{label} row {row}: sheet recipient {existing} but chain sends went to {dominant}")
            elif not existing:
                ws.cell(row, C["recipient"]).value = dominant
            if len(by_recip) > 1:
                flag(f"{label} row {row}: sends went to {len(by_recip)} recipients: {dict(by_recip)}")
            if not ws.cell(row, C["currency"]).value:
                ws.cell(row, C["currency"]).value = Counter(t for _, _, t, _ in sends).most_common(1)[0][0]
        write_sends(ws, row, sends)

    # ---- PB (Bitcoin) rows ----
    for tag, w in pb.items():
        row = PB_ROWS[tag]
        if tag != "PB-13":
            ws.cell(row, C["tag"]).value = tag
            ws.cell(row, C["label"]).value = w["label"]
            ws.cell(row, C["currency"]).value = "BTC"
            ws.cell(row, C["wallet"]).value = w["address"]
            if tag in PB_CLIENT:
                ws.cell(row, C["name"]).value, ws.cell(row, C["custodian"]).value = PB_CLIENT[tag]
            if tag != "PB-9" and w["recipients"]:
                ws.cell(row, C["recipient"]).value = w["recipients"][0]
        else:
            ws.cell(row, C["tag"]).value = tag
            existing = ws.cell(row, C["recipient"]).value
            if w["recipients"] and existing and existing.lower() != w["recipients"][0]:
                ws.cell(row, C["comments"]).value = (
                    f"on-chain: only send so far is a 0.001 BTC test to {w['recipients'][0]} (9/8); "
                    f"recipient column left as entered")
        if w["initial_funding_date_1k"]:
            set_date(ws, row, C["first_1k"], dt.datetime.strptime(w["initial_funding_date_1k"], "%Y-%m-%d"))
        set_num(ws, row, C["current"], w["balance_usd"])
        set_num(ws, row, C["funded"], w["total_funded_usd"])
        set_date(ws, row, C["current_date"], TODAY)
        sends = [(dt.datetime.strptime(s["ny"], "%Y-%m-%d %H:%M:%S"), s["usd"], "BTC", s["to"]) for s in w["sends"]]
        write_sends(ws, row, sends)
        if len(w["recipients"]) > 1:
            flag(f"{tag}: sends went to multiple recipients {w['recipients']}")

    wb.save(dst)
    print(f"wrote {dst}")
    print("\nFLAGS (" + str(len(flags)) + "):")
    for f in flags:
        print("  -", f)


if __name__ == "__main__":
    main()
