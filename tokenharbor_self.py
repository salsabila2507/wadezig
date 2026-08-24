#!/usr/bin/env python3
"""TokenHarbor signup — self-contained, no license needed.

Replicates the working signup flow (Next.js Server Action) and rotates
through a proxy list. No license gate, no dependency on the vendor bot.

Usage:
  python tokenharbor_self.py [count] [proxy_file]

  proxy_file : one proxy per line, format  user:pass@ip:port  or  ip:port
               (default: proxies.txt in this folder)
  count      : how many accounts to attempt (default: all proxies)

Optional: set CAPSOLVER_API_KEY env to solve Cloudflare Turnstile.
"""
import os, re, sys, time, json, random, string, uuid, urllib.parse
import requests

BASE = "https://tokenharbor.ai"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"
ACTION_ID = "6003703e71fc5dc99543154237e9a9267997419301"
ACTION_KEY = "kb59e6b88b9f36883e58e38e7e48870c6"
NEXT_ACTION = "607ec2c1a962aa81ad67a2483c54b0cfadfda875b2"
ROUTER = urllib.parse.quote('["",{"children":["login",{"children":["__PAGE__",{},null,null,0]},null,null,0]},null,null,20]')
TEST_MODEL = "mimo-v2.5:free"
HERE = os.path.dirname(os.path.abspath(__file__))
APIKEY_FILE = os.path.join(HERE, "apikeys.txt")
ACCOUNT_FILE = os.path.join(HERE, "accounts.json")
CAPSOLVER_API_KEY = os.environ.get("CAPSOLVER_API_KEY", "")


def log(msg, level="INFO"):
    print(f"  [{time.strftime('%H:%M:%S')}] [{level}] {msg}")


def rand_pwd():
    return "".join(random.choices(string.ascii_letters + string.digits, k=12)) + "!Aa1"


def load_accounts():
    if os.path.exists(ACCOUNT_FILE):
        with open(ACCOUNT_FILE) as f:
            return json.load(f)
    return []


def save_accounts(data):
    with open(ACCOUNT_FILE, "w") as f:
        json.dump(data, f, indent=2)


def load_keys():
    if os.path.exists(APIKEY_FILE):
        with open(APIKEY_FILE) as f:
            return [l.strip() for l in f if l.strip()]
    return []


def save_key(key):
    with open(APIKEY_FILE, "a") as f:
        f.write(f"{key}\n")


def make_signup_body(email, pwd):
    fp = str(uuid.uuid4())
    bd = "----WebKitFormBoundary" + "".join(random.choices(string.ascii_uppercase + string.digits, k=16))
    parts = []

    def af(n, v=""):
        parts.append(f"--{bd}\r\nContent-Disposition: form-data; name=\"{n}\"\r\n\r\n{v}")

    af("1_$ACTION_REF_1")
    af("1_$ACTION_1:0", json.dumps({"id": ACTION_ID, "bound": "$@1"}))
    af("1_$ACTION_1:1", '["$undefined"]')
    af("1_$ACTION_KEY", ACTION_KEY)
    af("1_device_fingerprint", fp)
    af("1_timezone")
    af("1_next")
    af("1_email", email)
    af("1_password", pwd)
    af("1_invite_code")
    af("0", '["$undefined","$K1"]')
    ct = os.environ.get("_CAPTCHA_TOKEN", "")
    if ct:
        af("cf-turnstile-response", ct)
    body = "\r\n".join(parts) + f"\r\n--{bd}--\r\n"
    headers = {
        "Content-Type": f"multipart/form-data; boundary={bd}",
        "Accept": "text/x-component",
        "Next-Action": NEXT_ACTION,
        "Next-Router-State-Tree": ROUTER,
        "Origin": BASE,
        "Referer": f"{BASE}/login",
    }
    return body, headers


def test_free_model(api_key, proxy):
    try:
        r = requests.post(f"{BASE}/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            timeout=30, json={"model": TEST_MODEL, "messages": [{"role": "user", "content": "say ok"}], "max_tokens": 20},
            proxies=proxy or None)
        if r.status_code == 200:
            reply = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")
            return True, f"200 OK - {reply[:30]}"
        return False, f"{r.status_code} - {r.text[:60]}"
    except Exception as e:
        return False, f"ERR - {str(e)[:50]}"


def extract_sitekey(html):
    for pat in [r'sitekey["\s:=]+["\']([^"\']+)', r'data-sitekey="([^"]+)"', r'0x4AAAAAA[^\s"\']+']:
        m = re.search(pat, html)
        if m:
            return m.group(1)
    return None


def solve_turnstile(sitekey, url):
    if not CAPSOLVER_API_KEY:
        return None
    try:
        r = requests.post("https://api.capsolver.com/createTask", json={
            "clientKey": CAPSOLVER_API_KEY,
            "task": {"type": "AntiTurnstileTaskProxyLess", "websiteURL": url, "websiteKey": sitekey}}, timeout=30)
        data = r.json()
        if data.get("errorId"):
            log(f"[CAPTCHA] Error: {data.get('errorDescription')}", "ERROR")
            return None
        task_id = data["taskId"]
        for _ in range(30):
            time.sleep(3)
            r2 = requests.post("https://api.capsolver.com/getTaskResult",
                json={"clientKey": CAPSOLVER_API_KEY, "taskId": task_id}, timeout=15)
            res = r2.json()
            if res.get("status") == "ready":
                return res["solution"].get("token", "")
            if res.get("errorId"):
                return None
        return None
    except Exception as e:
        log(f"[CAPTCHA] Exception: {e}", "ERROR")
        return None


def verify_email(email_token, proxy, max_wait=90):
    start = time.time()
    while time.time() - start < max_wait:
        try:
            r = requests.get(f"https://api.tempmail.lol/v2/inbox?token={email_token}", timeout=10, proxies=proxy or None)
            for em in r.json().get("emails", []):
                links = re.findall(r"https://tokenharbor\.ai/verify-email\?[^\s\"<>]+", em.get("body", ""))
                if links:
                    requests.get(links[0], timeout=15, allow_redirects=True, proxies=proxy or None)
                    return True
        except Exception:
            pass
        time.sleep(8)
    return False


def register_one(proxy):
    log("Creating temp email...")
    email_r = requests.post("https://api.tempmail.lol/v2/inbox/create", timeout=10, proxies=proxy or None)
    email = email_r.json()["address"]
    email_token = email_r.json()["token"]
    pwd = rand_pwd()
    log(f"Email: {email}")
    s = requests.Session()
    s.headers.update({"User-Agent": UA})
    log("Loading login page...")
    for attempt in range(5):
        try:
            s.get(f"{BASE}/login", proxies=proxy or None, timeout=20)
            break
        except Exception:
            log(f"  Retry {attempt+1}/5...", "WARN")
            time.sleep(3)
    log("Submitting signup...")
    try:
        page = s.get(f"{BASE}/login", proxies=proxy or None, timeout=20).text
        sk = extract_sitekey(page)
        if sk and CAPSOLVER_API_KEY:
            log(f"  Turnstile detected, solving...")
            tok = solve_turnstile(sk, f"{BASE}/login")
            if tok:
                os.environ["_CAPTCHA_TOKEN"] = tok
        elif sk:
            log("  Turnstile detected but no CAPSOLVER_API_KEY; trying without", "WARN")
        else:
            log("  No Turnstile found, trying without CAPTCHA")
    except Exception as e:
        log(f"CAPTCHA detection error: {e}", "WARN")
    body, headers = make_signup_body(email, pwd)
    for attempt in range(5):
        try:
            r = s.post(f"{BASE}/login", data=body, headers=headers, proxies=proxy or None, timeout=25)
            break
        except Exception:
            log(f"  Retry {attempt+1}/5...", "WARN")
            time.sleep(3)
    else:
        return None, "proxy failed after 5 retries"
    if "signedIn" not in r.text:
        errors = re.findall(r'"error":"([^"]+)"', r.text)
        err = errors[0] if errors else f"HTTP {r.status_code}"
        log(f"Signup FAILED: {err}", "ERROR")
        return None, err
    uid = re.findall(r'"userId":\s*"([^"]+)"', r.text)
    log(f"Signup OK - userId: {uid[0] if uid else '?'}")
    log("Cleaning auto-created keys...")
    r2 = s.get(f"{BASE}/api/keys", headers={"Accept": "application/json"}, proxies=proxy or None, timeout=15)
    for k in r2.json().get("keys", []):
        s.delete(f"{BASE}/api/keys/{k['id']}", proxies=proxy or None, timeout=10)
    log("Creating API key...")
    r3 = s.post(f"{BASE}/api/keys", json={"label": f"self-{random.randint(100,999)}"},
        headers={"Accept": "application/json", "Content-Type": "application/json"}, proxies=proxy or None, timeout=15)
    if r3.status_code != 201:
        log(f"Key create FAILED: {r3.status_code}", "ERROR")
        return None, f"key create failed {r3.status_code}"
    key = r3.json().get("plaintext")
    if not key:
        log("No plaintext in response", "ERROR")
        return None, "no plaintext"
    log(f"Key created: {key[:35]}...")
    log("Accepting free model consent...")
    rc = s.post(f"{BASE}/api/me/privacy", json={"free_models_enabled": True},
        headers={"Accept": "application/json", "Content-Type": "application/json"}, proxies=proxy or None, timeout=10)
    consent_ok = rc.status_code == 200 and '"ok":true' in rc.text
    log(f"Consent: {'Y' if consent_ok else 'N'} ({rc.status_code})")
    log("Waiting for verification email (max 90s)...")
    verified = verify_email(email_token, proxy)
    log(f"Email {'verified' if verified else 'NOT verified (timeout)'}")
    return {"email": email, "password": pwd, "userId": uid[0] if uid else "",
            "api_key": key, "email_token": email_token, "verified": verified, "consent": consent_ok}, None


def main():
    proxy_file = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "proxies_ips.txt")
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 10**9
    if not os.path.exists(proxy_file):
        print(f"Proxy file not found: {proxy_file}")
        return
    proxies = [l.strip() for l in open(proxy_file) if l.strip()]
    if not proxies:
        print("No proxies in file")
        return
    count = min(count, len(proxies))
    accounts = load_accounts()
    ok = 0
    for i in range(count):
        line = proxies[i]
        proxy = {"http": f"http://{line}", "https": f"http://{line}"}
        print(f"\n[{i+1}/{count}] {line}")
        try:
            acc, err = register_one(proxy)
        except Exception as e:
            acc, err = None, str(e)[:80]
        if acc:
            accounts.append(acc)
            save_accounts(accounts)
            save_key(acc["api_key"])
            t_ok, info = test_free_model(acc["api_key"], proxy)
            v = "Y" if acc.get("verified") else "N"
            c = "Y" if acc.get("consent") else "N"
            m = "Y" if t_ok else "N"
            print(f"  RESULT: {acc['email']} [verify:{v}] [consent:{c}] [model:{m}] key={acc['api_key'][:35]}...")
            ok += 1
        else:
            print(f"  FAILED: {err}")
    print(f"\n=== Done: {ok}/{count} accounts created ===")
    print(f"Keys saved to: {APIKEY_FILE}")


if __name__ == "__main__":
    main()
