# TokenHarbor Bulk Signup (no-license)

Self-contained TokenHarbor account creator. **No license, no dependency on the
vendor bot, no keygen.** Just proxies.

## What you need to add
1. `requests` — `pip install -r requirements.txt`
2. A proxy list in `proxies_ips.txt` (one proxy per line, format
   `user:pass@ip:port` or plain `ip:port`)
3. *(optional)* `CAPSOLVER_API_KEY` env var — only if you want Cloudflare
   Turnstile solved automatically. Without it, just rotate **fresh** proxies.

That's it. No license file, no payment, no `@machine_id_bot`.

## Usage
```
python tokenharbor_self.py [count] [proxy_file]
```
- `count`      : how many accounts to attempt (default: all proxies in file)
- `proxy_file` : proxy list path (default: `proxies_ips.txt` in this folder)

Each attempt creates a temp email, signs up via TokenHarbor's Next.js Server
Action endpoint, creates an API key, accepts the free-model consent, and verifies
the email. Keys are appended to `apikeys.txt`; accounts to `accounts.json`.

## How it works
Reimplements the signup flow (the same HTTP calls the vendor bot uses) with proxy
rotation. The vendor bot's license gate lives only in `bot.py`; the signup logic
is plain HTTP and is reproduced here cleanly.

## Refilling proxies
When proxies get flagged by Cloudflare, get fresh ones, e.g. proxyscrape:
```
curl -s "https://api.proxyscrape.com/?request=getproxies&proxytype=http&limit=100&apiKey=YOUR_PROXYSCRAPE_TOKEN&format=normal" > proxies_ips.txt
```
Then just re-run `python tokenharbor_self.py`.

## Notes
- `tokenharbor_signup.py` is the older curl-based variant (kept for reference).
- Free/shared proxies get flagged fast — prefer private/residential or rotate often.
- `proxies_ips.txt`, `apikeys.txt`, `accounts.json` are gitignored (don't commit them).
