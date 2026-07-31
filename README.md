# Crypto Address Balance Querier

Paste a list of EVM wallet addresses into a local web GUI, fetch each wallet's
cross-chain portfolio (total USD value, per-chain breakdown, top tokens, DeFi
positions, optional NFT value), and export the results as a copy-pastable /
downloadable CSV.

## Quick start

```bash
python3 server.py
# then open http://127.0.0.1:8787 in your browser
```

No dependencies — Python 3.8+ standard library only. The server exists because
the data providers don't allow browser cross-origin requests; it serves the GUI
and forwards API calls. Your API key stays in your browser (optionally in
localStorage if you tick "Remember key") and is only forwarded per-request.

Try it immediately with **Demo mode** (provider dropdown) — generates fake data
with no key and no API calls.

## Data providers

| Provider | Cost / gating | Coverage | Requests per wallet |
|---|---|---|---|
| **Zerion** (default) | Free API key — email signup at [developers.zerion.io](https://developers.zerion.io), no payment, no KYC | All major EVM chains in one call: totals, per-chain breakdown, wallet tokens with prices, DeFi positions by protocol, NFT floor value | 2 (3 with NFTs) |
| **DeBank Pro** | Paid — prepaid "units" at [cloud.debank.com](https://cloud.debank.com) | The deepest DeFi/protocol coverage and NFT item lists | 2–4 |

Both are supported; pick in the GUI's provider dropdown. Zerion's free tier is
comfortably enough for 50 wallets (its rate limits are per-second, not a tiny
monthly cap). If you ever want DeBank's deeper protocol detail, buy units and
switch the dropdown — no code changes.

Other options considered and why they're not wired in:

- **Moralis** — free tier exists, but it prices per chain per wallet
  (net-worth alone is 250 compute units *per chain*), so 50 wallets × several
  chains exhausts the free daily allowance. Zerion does the same job in one call.
- **Covalent/GoldRush, Alchemy Portfolio API** — fine free tiers but per-chain
  queries and weaker DeFi position data.
- **No-signup (public RPCs/explorers)** — possible but you lose USD pricing,
  DeFi positions, and cross-chain aggregation; you'd only get raw balances.

## Using the GUI

1. Pick a provider and paste your API key (Demo mode needs none).
2. Paste addresses — one per line; labels/extra text after an address are
   ignored; duplicates are dropped.
3. Choose what to include: wallet tokens, DeFi positions, NFT value.
4. Fetch. Results stream into the table as wallets complete; failures show an
   error per row without stopping the run.
5. Export from either tab:
   - **Summary** — one row per wallet: `total_usd`, `wallet_tokens_usd`,
     `defi_usd`, optional NFT columns, per-chain USD breakdown, top-N assets
     and top DeFi positions (compact `SYMBOL amount ($usd) [chain]` strings).
   - **Details** — one row per asset/position: type (token/defi/nft), chain,
     symbol, amount, price, USD value, protocol.

CSV numbers are plain (no `$`, no thousands separators) so spreadsheets parse
them directly.

## Notes

- Addresses must be EVM (`0x` + 40 hex chars). Zerion also accepts Solana
  addresses via its API, but the GUI currently validates EVM format only.
- "Ignore assets under (USD)" filters dust from token/position lists; it
  doesn't change the wallet totals reported by the provider.
- **"Verified tokens only" (default on)** drops tokens the provider hasn't
  verified — typically scam airdrops with fabricated prices that can inflate a
  wallet by hundreds of thousands of fake dollars. With Zerion, totals and the
  per-chain breakdown are recomputed from verified positions (loans subtracted),
  since Zerion's own portfolio total includes unverified tokens. Untick it to
  see the raw provider numbers.
- Zerion returns HTTP 202 while it indexes a wallet it hasn't seen before;
  the client retries automatically for a couple of minutes.
- Airdrop eligibility isn't exposed by any of these portfolio APIs; per-project
  eligibility checkers are the only reliable source for that.
