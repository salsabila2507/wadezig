# AGENTS.md — run this project directly

You are helping operate the **TokenHarbor bulk signup** tool. TokenHarbor is a
standalone LLM API provider (`https://tokenharbor.ai`, OpenAI-style `/v1`, free
model `mimo-v2.5:free`, key prefix `thk_live_`). It is **not** "OpenCode Zen".

## Goal
Create N TokenHarbor accounts + API keys via rotating HTTP proxies, append the
keys to a file. The user pastes those keys into their client (e.g. 9Router /
OpenCode as a `tokenbor` provider: `baseUrl=https://tokenharbor.ai/v1`,
`model=mimo-v2.5:free`, `auth=api_key`).

## Hard constraints (do NOT skip — learned empirically)
1. **One account per proxy IP.** After 1 successful signup, that IP is flagged
   and returns `Please complete the human check to continue` forever.
2. **Cloudflare is aggressive & flaky.** Even a fresh IP may return `HTTP 200`
   (challenge) instead of `303 signedIn`. Retrying the *same* proxy later can
   pass. The script already retries a proxy 3× before rotating.
3. **The machine's own IP gets flagged after 1 success** — always use proxies.
4. Success rate through datacenter proxies is low (can drop to ~1%). Expect to
   burn many proxies for few keys. This is expected, not a bug.

## Setup (from a clean checkout)
```bash
cd <repo>
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
```
Put your proxy IPs (one per line) in `proxies_ips.txt`, then:
```bash
export TH_PROXY_AUTH="user:pass"      # proxy credential (leave empty for open proxies)
export TH_PROXY_PORT="3129"           # or your proxy port (only used when a line is host-only)
# optional single-proxy override (phone tunnel):
# export TH_PROXY="socks5h://127.0.0.1:1081"
```
The working method that produced real keys: a list of datacenter proxy IPs
(one per line) + `TH_PROXY_AUTH`/`TH_PROXY_PORT`, rotated 1 IP per account with
retry/grind. **Each IP yields at most 1 account** (then Cloudflare flags it).

Accepted `proxies_ips.txt` line formats (all parsed automatically):
```
ip                 # host only -> uses TH_PROXY_PORT + TH_PROXY_AUTH
ip:port           # host:port
user:pass@ip:port # auth + host:port
```

Optional convenience (often yields DEAD public proxies — low success):
`python tokenharbor_signup.py fetch` pulls free `ip:port` HTTP proxies from
ProxyScrape (`https://proxyscrape.com`) into `proxies_ips.txt`. Prefer your own
authenticated/residential list for reliable bulk creation.

## Run
```bash
# bulk: attempt COUNT signups, stop when TH_TARGET keys collected
TH_TARGET=20 python tokenharbor_signup.py 40

# grind: loop ALL proxies repeatedly until TH_TARGET new keys collected
TH_MODE=grind TH_TARGET=20 python tokenharbor_signup.py
```
Keys append to `TH_KEYS_FILE` (default `./tokenharbor_apikeys.txt`). Re-running
adds to the file (dedup-friendly: don't re-add already-collected keys).

## If it stalls (0–1 keys after many attempts)
- Cloudflare likely tightened. Options, in order of effort:
  1. Keep `grind` running — flaky proxies occasionally pass on later passes.
  2. Get a fresher / residential proxy list (more distinct IPs = more accounts).
  3. Implement a headless-browser Cloudflare Turnstile solver (the signup POST
     is what gets challenged; a real browser through the proxy often passes).
- Never assume a proxy is "dead" from one `HTTP 404`/`HTTP 200` — it is often
  transient. The script's 3× same-proxy retry handles this.

## Delivering keys to the user
Keys are in `TH_KEYS_FILE`. If running on a remote box, do NOT expose the port
to the internet. Use:
```bash
scp user@host:/abs/path/tokenharbor_apikeys.txt .
# or: on server `python3 -m http.server 8899 --directory <dir>`,
#     on laptop `ssh -N -L 8899:localhost:8899 user@host` then open
#     http://localhost:8899/tokenharbor_apikeys.txt
```

## Files
- `tokenharbor_signup.py` — main script (single / bulk / grind modes).
- `proxies_ips.txt` — your proxy IPs (git-ignored; use `proxies_ips.example.txt`).
- `tokenharbor_apikeys.txt` — output keys (git-ignored).
- `README.md` — full human docs + troubleshooting.
