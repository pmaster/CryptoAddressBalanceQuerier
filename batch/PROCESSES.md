# Named processes

## "Update crypto funds UCF"

Triggered by the user saying exactly that phrase. Steps:

1. Refresh and display current balances for the 10 "funds" wallets
   (`batch/wallets_refresh10.txt`: Adamo OTC, Brute OTC, SP4-1..SP4-8),
   and sum them.
2. Refresh balances + swap-aware net funding (`batch/net_funding.py`)
   for SP4-9 through SP4-50 (`batch/wallets_sp4_9_50.txt`), and print
   a tab-separated, unlabeled copy-paste block — one row per wallet in
   SP4-9..SP4-50 order — with columns:
   `Initial Funding Date >$1k`, `Current Funds`, `Total Funded to Wallet`.

Requires: local server running (`python3 server.py --port 8787`) and
`ZERION_KEY` set. Commands:

```
python3 batch/inbounds.py batch/wallets_refresh10.txt --prefix ucf10
python3 batch/inbounds.py batch/wallets_sp4_9_50.txt --prefix ucf42
python3 batch/net_funding.py batch/wallets_sp4_9_50.txt --prefix ucf42
```

If new wallets are added to either list in a future run, validate hex
format and cross-check any addresses claimed to already be known
against the prior mapping before trusting them (see git history for
the false-positive/typo checks this caught previously).
