#!/usr/bin/env python3
"""tokenharbor_signup.py

Bulk-create TokenHarbor accounts + API keys via rotating HTTP proxies.

TokenHarbor is a standalone LLM API provider (https://tokenharbor.ai), API-OpenAI
style: base URL https://tokenharbor.ai/v1, free model "mimo-v2.5:free",
key prefix "thk_live_". This script signs up N accounts (temp email) and writes
one API key per account to a file.

================================================================================
IMPORTANT — what we learned the hard way (read before running)
================================================================================
* TokenHarbor is behind Cloudflare. A given proxy IP can register EXACTLY ONE
  account, then that IP gets challenged ("Please complete the human check to
  continue"). Re-using the same IP => permanent challenge for signup.
* Success rate through datacenter proxies is LOW and FLUCTUATES. Sometimes a
  fresh proxy returns HTTP 200 (Cloudflare interstitial) even on first use;
  retrying the SAME proxy a few minutes later may pass. So we retry + rotate.
* The server's own IP gets captcha-flagged after the first success too. Always
  go through a proxy / phone tunnel.
* Each working proxy yields at most 1 key. To get M keys you need (at least) M
  distinct, currently-unflagged proxy IPs (plus retries for the flaky ones).

================================================================================
Usage
================================================================================
  # single account (uses proxies_ips.txt, rotating)
  python tokenharbor_signup.py 1

  # bulk: try 40 signups, stop as soon as we have 20 keys
  TH_TARGET=20 python tokenharbor_signup.py 40

  # grind: loop over ALL proxies repeatedly until 20 NEW keys collected
  TH_MODE=grind TH_TARGET=20 python tokenharbor_signup.py

Environment (all optional):
  TH_PROXY_IPS     file with one proxy IP per line   (default: ./proxies_ips.txt)
  TH_PROXY_AUTH    "user:pass" for the proxies        (default: empty)
  TH_PROXY_PORT    proxy port                          (default: 3129)
  TH_PROXY         single proxy override, e.g.
                   socks5h://127.0.0.1:1081 (phone tunnel)  (default: empty)
  TH_KEYS_FILE     where to append keys               (default: ./tokenharbor_apikeys.txt)
  TH_TARGET        stop / goal count                  (default: 10)
  TH_PROXY_OFFSET  start proxy index                  (default: 0)
  TH_MODE          "bulk" (default) | "grind"
"""
import curl_cffi.requests as creq, re, json, random, string, uuid, time, os, sys, urllib.parse

BASE = "https://tokenharbor.ai"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"
ACTION_ID = "6003703e71fc5dc99543154237e9a9267997419301"
ACTION_KEY = "kb59e6b88b9f36883e58e38e7e48870c6"
NEXT_ACTION = "607ec2c1a962aa81ad67a2483c54b0cfadfda875b2"
ROUTER = urllib.parse.quote('["",{"children":["login",{"children":["__PAGE__",{},null,null,0]},null,null,0]},null,null,20]')
TEST_MODEL = "mimo-v2.5:free"
ACCOUNT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tokenharbor_accounts.json")

# ---- config from env ----
PROXY_AUTH = os.environ.get("TH_PROXY_AUTH", "")
PROXY_PORT = os.environ.get("TH_PROXY_PORT", "3129")
PROXY_IPS_FILE = os.environ.get("TH_PROXY_IPS", os.path.join(os.path.dirname(os.path.abspath(__file__)), "proxies_ips.txt"))
KEYS_FILE = os.environ.get("TH_KEYS_FILE", os.path.join(os.path.dirname(os.path.abspath(__file__)), "tokenharbor_apikeys.txt"))
TARGET = int(os.environ.get("TH_TARGET", "10"))
PROXY_OFFSET = int(os.environ.get("TH_PROXY_OFFSET", "0"))
MODE = os.environ.get("TH_MODE", "bulk").lower()
SINGLE_PROXY = os.environ.get("TH_PROXY", "")

PROXIES = None
if SINGLE_PROXY:
    PROXIES = {"http": SINGLE_PROXY, "https": SINGLE_PROXY}

s = creq.Session()
s.headers.update({"User-Agent": UA})

def log(m, lv="INFO"):
    print(f"  [{lv}] {m}")

def rand_pwd():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=12)) + '!Aa1'

def make_signup_body(email, pwd):
    fp = str(uuid.uuid4())
    bd = "----WebKitFormBoundary" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))
    parts = []
    def af(n, v=""):
        parts.append(f'--{bd}\r\nContent-Disposition: form-data; name="{n}"\r\n\r\n{v}')
    af("1_$ACTION_REF_1")
    af("1_$ACTION_1:0", json.dumps({"id": ACTION_ID, "bound": "$@1"}))
    af("1_$ACTION_1:1", '["$undefined"]')
    af("1_$ACTION_KEY", ACTION_KEY)
    af("1_device_fingerprint", fp); af("1_timezone"); af("1_next")
    af("1_email", email); af("1_password", pwd); af("1_invite_code")
    af("0", '["$undefined","$K1"]')
    body = "\r\n".join(parts) + f"\r\n--{bd}--\r\n"
    headers = {
        "Content-Type": f"multipart/form-data; boundary={bd}",
        "Accept": "text/x-component",
        "Next-Action": NEXT_ACTION,
        "Next-Router-State-Tree": ROUTER,
        "Origin": BASE, "Referer": f"{BASE}/login",
    }
    return body, headers

def create_temp_email():
    r = s.post("https://api.tempmail.lol/v2/inbox/create", timeout=10, proxies=PROXIES)
    d = r.json()
    return d["address"], d["token"]

def verify_email(token, max_wait=90):
    start = time.time()
    while time.time() - start < max_wait:
        try:
            r = s.get(f"https://api.tempmail.lol/v2/inbox?token={token}", timeout=8, proxies=PROXIES)
            for em in r.json().get("emails", []):
                links = re.findall(r'(https://tokenharbor\.ai/verify-email\?[^\s"<>]+)', em.get("body", ""))
                if links:
                    s.get(links[0], timeout=12, allow_redirects=True, proxies=PROXIES)
                    return True
        except Exception:
            pass
        time.sleep(4)
    return False

def test_free_model(api_key):
    try:
        r = s.post(f"{BASE}/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            timeout=15, proxies=PROXIES,
            json={"model": TEST_MODEL, "messages": [{"role": "user", "content": "say ok"}], "max_tokens": 20})
        if r.status_code == 200:
            reply = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
            return True, f"200 OK - {reply[:30]}"
        return False, f"{r.status_code} - {r.text[:60]}"
    except Exception as e:
        return False, f"ERR - {str(e)[:50]}"

def register_one():
    email, etok = create_temp_email()
    pwd = rand_pwd()
    log(f"Email: {email}")
    log("GET /login (load cookies)...")
    s.get(f"{BASE}/login", timeout=12, proxies=PROXIES)
    log("POST signup...")
    body, headers = make_signup_body(email, pwd)
    r = s.post(f"{BASE}/login", data=body, headers=headers, timeout=12, proxies=PROXIES)
    if "signedIn" not in r.text:
        errs = re.findall(r'"error":"([^"]+)"', r.text)
        err = errs[0] if errs else f"HTTP {r.status_code}"
        log(f"Signup FAILED: {err}", "ERROR"); return None, err
    uid = re.findall(r'"userId":\s*"([^"]+)"', r.text)
    log(f"Signup OK - userId: {uid[0] if uid else '?'}")
    # delete auto-created keys, then make one clean key
    r2 = s.get(f"{BASE}/api/keys", headers={"Accept": "application/json"}, timeout=15, proxies=PROXIES)
    for k in r2.json().get("keys", []):
        s.delete(f"{BASE}/api/keys/{k['id']}", timeout=10, proxies=PROXIES)
    log("Create API key...")
    r3 = s.post(f"{BASE}/api/keys", json={"label": f"bot-{random.randint(100,999)}"},
        headers={"Accept": "application/json", "Content-Type": "application/json"}, timeout=15, proxies=PROXIES)
    if r3.status_code != 201:
        log(f"Key create FAILED: {r3.status_code}", "ERROR"); return None, f"key fail {r3.status_code}"
    key = r3.json().get("plaintext")
    if not key:
        log("No plaintext", "ERROR"); return None, "no plaintext"
    log(f"Key: {key[:35]}...")
    log("Consent free model...")
    rc = s.post(f"{BASE}/api/me/privacy", json={"free_models_enabled": True},
        headers={"Accept": "application/json", "Content-Type": "application/json"}, timeout=10, proxies=PROXIES)
    consent = rc.status_code == 200 and '"ok":true' in rc.text
    log(f"Consent: {'Y' if consent else 'N'} ({rc.status_code})")
    log("Verify email (max 90s)...")
    verified = verify_email(etok)
    log(f"Email {'verified' if verified else 'NOT verified (timeout)'}")
    return {"email": email, "password": pwd, "userId": uid[0] if uid else "",
            "api_key": key, "verified": verified, "consent": consent}, None

def load_proxies():
    if SINGLE_PROXY:
        return []
    if not os.path.exists(PROXY_IPS_FILE):
        return []
    return [l.strip() for l in open(PROXY_IPS_FILE) if l.strip()]

def fetch_proxies():
    """Pull fresh HTTP proxies from ProxyScrape into PROXY_IPS_FILE.
    Usage:  python tokenharbor_signup.py fetch
    """
    url = ("https://api.proxyscrape.com/?request=getproxies&proxytype=http"
           "&timeout=10000&country=all&ssl=all&anonymity=all")
    print(f"  fetching proxies from proxyscrape...")
    try:
        r = creq.get(url, timeout=40)
    except Exception as e:
        print(f"  FETCH GAGAL: {e}"); return
    lines = [l.strip().replace("\r", "") for l in r.text.splitlines() if l.strip()]
    lines = [l for l in lines if re.match(r"^\d+\.\d+\.\d+\.\d+:\d+$", l)]
    os.makedirs(os.path.dirname(PROXY_IPS_FILE) or ".", exist_ok=True)
    with open(PROXY_IPS_FILE, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"  OK: {len(lines)} proxy tersimpan di {PROXY_IPS_FILE}")

def parse_proxy(line):
    """line forms accepted:
        ip                -> use TH_PROXY_PORT + TH_PROXY_AUTH
        ip:port           -> that port, TH_PROXY_AUTH
        user:pass@ip:port -> that auth + port
    """
    line = line.strip()
    auth = PROXY_AUTH
    if "@" in line:
        a, line = line.split("@", 1)
        auth = a or auth
    if ":" in line:
        host, _, port = line.rpartition(":")
        port = port or PROXY_PORT
    else:
        host, port = line, PROXY_PORT
    return host, port, auth

def set_proxy(idx):
    global PROXIES
    ips = load_proxies()
    if not ips:
        PROXIES = None; return None
    host, port, auth = parse_proxy(ips[idx % len(ips)])
    if auth:
        url = f"http://{auth}@{host}:{port}"
    else:
        url = f"http://{host}:{port}"
    PROXIES = {"http": url, "https": url}
    return f"{host}:{port}"

def have_key(k):
    try:
        return k in {l.strip() for l in open(KEYS_FILE) if l.strip()}
    except FileNotFoundError:
        return False

def count_keys():
    try:
        return sum(1 for l in open(KEYS_FILE) if l.strip())
    except FileNotFoundError:
        return 0

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "fetch":
        fetch_proxies()
        return
    count = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 1
    os.makedirs(os.path.dirname(KEYS_FILE), exist_ok=True)
    proxies = load_proxies()
    print("="*50)
    print(f"  TokenHarbor signup  mode={MODE}  target={TARGET}")
    if SINGLE_PROXY:
        print(f"  Proxy: {SINGLE_PROXY} (single)")
    elif proxies:
        print(f"  Proxies: {len(proxies)} from {PROXY_IPS_FILE}  (offset {PROXY_OFFSET})")
    else:
        print("  No proxies configured -> DIRECT (server IP, gets flagged fast)")
    print(f"  Keys -> {KEYS_FILE}")
    print("="*50)

    if MODE == "grind":
        grind()
        return

    # ---- bulk mode ----
    ok_total = 0
    pi = PROXY_OFFSET
    for i in range(count):
        ip = set_proxy(pi) if proxies else None
        print(f"\n--- [{i+1}/{count}] via {ip or 'DIRECT'} ---")
        acc = None
        same_retry = 0
        for attempt in range(12):
            try:
                a, err = register_one()
                if a:
                    acc = a; break
                print(f"  attempt {attempt+1} gagal: {err[:50]}")
            except Exception as e:
                print(f"  attempt {attempt+1} err: {str(e)[:50]}")
            same_retry += 1
            if same_retry >= 3:   # proxy flaky: retry 3x, then switch
                pi += 1
                if proxies: set_proxy(pi)
                same_retry = 0
            time.sleep(3)
        if not acc:
            print("  SKIP (gagal semua attempt)")
            pi += 1
            if i < count-1: time.sleep(10)
            continue
        ok, info = test_free_model(acc["api_key"])
        with open(KEYS_FILE, "a") as f:
            f.write(acc["api_key"] + "\n")
        data = []
        if os.path.exists(ACCOUNT_FILE):
            try: data = json.load(open(ACCOUNT_FILE))
            except: data = []
        acc["test"] = info; data.append(acc); json.dump(data, open(ACCOUNT_FILE, "w"), indent=2)
        ok_total += 1
        print(f"  KEY: {acc['api_key'][:30]}... | verify:{acc['verified']} consent:{acc['consent']} model:{'OK' if ok else 'FAIL'}")
        cur = count_keys()
        pi += 1
        if cur >= TARGET:
            print(f"  TARGET {TARGET} tercapai ({cur} key)")
            break
        if i < count-1:
            wait = random.randint(5, 12); print(f"  wait {wait}s..."); time.sleep(wait)
    print(f"\n  SELESAI: {ok_total}/{count} akun. Keys di {KEYS_FILE}")

def grind():
    """Loop over ALL proxies repeatedly until TARGET new keys collected."""
    proxies = load_proxies()
    if not proxies:
        print("grind butuh proxies_ips.txt + TH_PROXY_AUTH"); return
    got = 0
    ok_idx = set()
    MAX_PASS = 20
    for p in range(MAX_PASS):
        pk = 0
        for i in range(len(proxies)):
            if i in ok_idx: continue
            set_proxy(i)
            t0 = time.time()
            try:
                a, err = register_one()
            except Exception as e:
                print(f"[p{p}] idx {i} EXC {str(e)[:30]}"); continue
            if a and a["api_key"] and not have_key(a["api_key"]):
                with open(KEYS_FILE, "a") as f: f.write(a["api_key"] + "\n")
                ok_idx.add(i); got += 1; pk += 1
                print(f"[p{p}] idx {i:3d} OK +1 (total+{got}) key={a['api_key'][:20]} v={a['verified']}")
            elif a:
                ok_idx.add(i)  # dup, skip next pass
            time.sleep(1)
        print(f"=== pass {p} selesai: +{pk} di pass ini, total tambahan {got}/{TARGET} ===")
        if got >= TARGET:
            print("TARGET tercapai"); break
        time.sleep(5)
    print(f"GRIND DONE: +{got} tambahan. File: {KEYS_FILE}")

if __name__ == "__main__":
    main()
