# tokenharbor-bulk-signup

Bulk-create **TokenHarbor** accounts + API keys via rotating HTTP proxies.

> **Note:** TokenHarbor is a *standalone* LLM API provider
> (`https://tokenharbor.ai`, OpenAI-style `/v1`, free model `mimo-v2.5:free`,
> key prefix `thk_live_`). It is **not** "OpenCode Zen" — the two are separate
> services. This tool only creates TokenHarbor accounts/keys.

Each run signs up N accounts using throwaway emails and writes one API key per
account to a file you can then paste into your client (e.g. 9Router / OpenCode
as a `tokenbor` provider with `baseUrl=https://tokenharbor.ai/v1`,
`model=mimo-v2.5:free`).

---

## ⚠️ Read this first — what actually happens in production

TokenHarbor sits behind **Cloudflare**, and the signup endpoint is aggressively
challenged. We learned this the hard way:

1. **One account per IP.** A given proxy IP can register **exactly one**
   account, then that IP gets flagged and every later signup returns
   `Please complete the human check to continue` (HTTP 200 Cloudflare page).
2. **Success rate is low AND flaky.** Even on a never-used IP, signup may return
   `HTTP 200` (challenge) instead of `303 signedIn`. Retrying the *same* proxy a
   few minutes later sometimes passes. So we **retry + rotate**.
3. **The server's own IP gets flagged too** after the first success — always go
   through a proxy or a phone tunnel.
4. **Each working proxy yields at most 1 key.** To get `M` keys you need (at
   least) `M` distinct, currently-unflagged proxy IPs, plus retries for the
   flaky ones.

Real-world result: with ~100 datacenter proxies we got ~17 keys in one window,
then Cloudflare tightened and the same pool dropped to ~1% success. Plan
accordingly — this is not a fire-and-forget 100% success tool.

---

## Requirements

- Python 3.10+
- `curl_cffi` (for the TLS fingerprint that gets past Cloudflare more often)
- A list of HTTP proxies (`ip` per line) + their `user:pass` auth
- Internet access from the machine running the script

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
```

---

## Setup

1. Put your proxy IPs (one per line) in `proxies_ips.txt`:
   ```
   1.2.3.4
   5.6.7.8
   ...
   ```
   (See `proxies_ips.example.txt`.)

2. Export the proxy auth + port:
   ```bash
   export TH_PROXY_AUTH="youruser:yourpass"
   export TH_PROXY_PORT="3129"          # default
   ```

   Optional single-proxy override (e.g. a phone tunnel via `ssh -R` + microsocks):
   ```bash
   export TH_PROXY="socks5h://127.0.0.1:1081"
   ```

---

## Usage

```bash
# single account
python tokenharbor_signup.py 1

# bulk: attempt 40 signups, stop as soon as 20 keys are collected
TH_TARGET=20 python tokenharbor_signup.py 40

# grind: loop over ALL proxies repeatedly until 20 NEW keys collected
TH_MODE=grind TH_TARGET=20 python tokenharbor_signup.py
```

### Environment variables

| Var | Default | Meaning |
|-----|---------|---------|
| `TH_PROXY_IPS` | `./proxies_ips.txt` | file with one proxy IP per line |
| `TH_PROXY_AUTH` | _(empty)_ | `user:pass` for the proxies |
| `TH_PROXY_PORT` | `3129` | proxy port |
| `TH_PROXY` | _(empty)_ | single proxy override (e.g. `socks5h://127.0.0.1:1081`) |
| `TH_KEYS_FILE` | `./tokenharbor_apikeys.txt` | where keys are appended |
| `TH_TARGET` | `10` | stop / goal count |
| `TH_PROXY_OFFSET` | `0` | start proxy index |
| `TH_MODE` | `bulk` | `bulk` or `grind` |

Keys are appended (not overwritten) so re-running adds to the file.

---

## Getting the keys off the server

Keys land in `TH_KEYS_FILE` (default `tokenharbor_apikeys.txt`). To copy them
from a remote box without exposing the port to the internet, use **scp** or an
**SSH local forward**:

```bash
# option A — scp
scp user@host:/path/tokenharbor_apikeys.txt .

# option B — SSH tunnel + browser (port 8899 served only on localhost)
# on the server:  python3 -m http.server 8899 --directory /path/to/keysdir
# on your laptop:
ssh -N -L 8899:localhost:8899 user@host
# then open http://localhost:8899/tokenharbor_apikeys.txt
```

---

## Using the keys

TokenHarbor is OpenAI-compatible:

- **base URL:** `https://tokenharbor.ai/v1`
- **model:** `mimo-v2.5:free`
- **Authorization:** `Bearer thk_live_xxx`

For 9Router / OpenCode, add a provider named `tokenbor` with
`auth=api_key`, `baseUrl=https://tokenharbor.ai/v1`,
`defaultModel=mimo-v2.5:free`, and paste the key.

---

## Troubleshooting

| Symptom | Cause / Fix |
|---------|-------------|
| `Please complete the human check` | Proxy IP already flagged. Rotate to a fresh IP. |
| `HTTP 200` with no `signedIn` | Cloudflare interstitial (challenge). Proxy is flaky/flagged — retry or switch. |
| `HTTP 404` from proxy | Transient proxy glitch — the script retries the same proxy 3× before switching; usually recovers. |
| `tempmail.lol` errors | Temp-mail API hiccup — just re-run, a new email is generated each attempt. |
| 0 keys after many tries | Cloudflare tightened; your proxy pool is mostly flagged. Need fresher/residential proxies, or a browser-based Turnstile solver. |

---

## Disclaimer

For personal/educational automation. Respect TokenHarbor's Terms of Service and
don't abuse the free tier. Use responsibly.
