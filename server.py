#!/usr/bin/env python3
"""Crypto Address Balance Querier — local server.

Serves the web GUI (index.html) and proxies API calls to the selected
data provider. A local proxy is required because these APIs do not
allow cross-origin requests directly from a browser page.

Supported providers:
  - zerion : https://api.zerion.io          (free API key, no payment)
  - debank : https://pro-openapi.debank.com (paid units)

Runs on the Python standard library only — no pip installs needed.

Usage:
    python3 server.py [--port 8787] [--host 127.0.0.1]

Your API key is entered in the GUI and forwarded per-request via the
X-Access-Key header; it is never stored on the server.
"""

import argparse
import base64
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
ADDR = r"0x[0-9a-fA-F]{40}"

# provider -> (base URL, allowed endpoint patterns)
PROVIDERS = {
    "debank": (
        "https://pro-openapi.debank.com/v1/",
        [re.compile(r"^user/(total_balance|all_token_list|all_complex_protocol_list|all_nft_list)$")],
    ),
    "zerion": (
        "https://api.zerion.io/v1/",
        [re.compile(rf"^wallets/{ADDR}/(portfolio|positions/|nft-portfolio)$")],
    ),
}

UPSTREAM_TIMEOUT = 90  # seconds; token/position lists can be slow for big wallets


def auth_header(provider, key):
    if provider == "debank":
        return "AccessKey", key
    # Zerion uses HTTP basic auth: API key as username, empty password.
    token = base64.b64encode(f"{key}:".encode()).decode()
    return "Authorization", f"Basic {token}"


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        parsed = urllib.parse.urlsplit(self.path)
        path = parsed.path

        if path in ("/", "/index.html"):
            self._serve_file("index.html", "text/html; charset=utf-8")
        elif path.startswith("/api/"):
            parts = path[len("/api/"):].split("/", 1)
            if len(parts) == 2:
                self._proxy(parts[0], parts[1], parsed.query)
            else:
                self._send(404, b'{"error":"bad api path"}')
        else:
            self._send(404, b'{"error":"not found"}')

    def _serve_file(self, name, ctype):
        try:
            with open(os.path.join(ROOT, name), "rb") as f:
                body = f.read()
        except OSError:
            self._send(404, b"file not found", "text/plain")
            return
        self._send(200, body, ctype)

    def _proxy(self, provider, endpoint, query):
        if provider not in PROVIDERS:
            self._send(403, b'{"error":"unknown provider"}')
            return
        base, patterns = PROVIDERS[provider]
        if not any(p.match(endpoint) for p in patterns):
            self._send(403, b'{"error":"endpoint not allowed"}')
            return

        access_key = self.headers.get("X-Access-Key", "").strip()
        if not access_key:
            self._send(401, b'{"error":"missing X-Access-Key header"}')
            return

        url = base + endpoint + ("?" + query if query else "")
        name, value = auth_header(provider, access_key)
        req = urllib.request.Request(url, headers={
            name: value,
            "Accept": "application/json",
            "User-Agent": "CryptoAddressBalanceQuerier/1.0",
        })
        try:
            with urllib.request.urlopen(req, timeout=UPSTREAM_TIMEOUT) as resp:
                self._send(resp.status, resp.read())
        except urllib.error.HTTPError as e:
            self._send(e.code, e.read() or b'{"error":"upstream error"}')
        except Exception as e:  # DNS failure, timeout, TLS, ...
            msg = '{"error":"proxy request failed: %s"}' % str(e).replace('"', "'")
            self._send(502, msg.encode())

    def _send(self, status, body, ctype="application/json"):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        # Keep the console quiet except for error responses.
        if args and len(args) > 1 and str(args[1]).startswith(("4", "5")):
            super().log_message(fmt, *args)


def main():
    ap = argparse.ArgumentParser(description="Crypto Address Balance Querier server")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Crypto Address Balance Querier running at http://{args.host}:{args.port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
