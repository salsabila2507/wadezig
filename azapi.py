"""
AZAPI client — GMI Cloud document / OCR & captcha API.

Base URLs
  https://api.azapi.ai    CAPTCHA solver      (t0001c, m0001c/1)
  https://ocr.azapi.ai    OCR / KYC / Bank    (g0002d, ind*, bank*, ov*)

Auth
  Header:  Authorization: <AZAPI_KEY>     (NO "Bearer" prefix)

Request body
  Raw image bytes, Content-Type: image/jpeg

See AZAPI.md for the full endpoint list & examples.
"""
import os
import requests


def _key():
    k = os.environ.get("AZAPI_KEY")
    if k:
        return k
    # fallback: read local .env (gitignored)
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    try:
        for line in open(p):
            line = line.strip()
            if line.startswith("AZAPI_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    raise RuntimeError("AZAPI_KEY not set. Export it or put AZAPI_KEY=... in .env")


def _post(url, image):
    if isinstance(image, (bytes, bytearray)):
        data = bytes(image)
    elif isinstance(image, str):
        with open(image, "rb") as f:
            data = f.read()
    else:
        raise ValueError("image must be a file path or bytes")
    headers = {"Authorization": _key(), "Content-Type": "image/jpeg"}
    r = requests.post(url, data=data, headers=headers, timeout=60)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, r.text


# Common endpoints (use the key, or pass a full URL to the helpers below)
ENDPOINTS = {
    "captcha_text":   "https://api.azapi.ai/t0001c",
    "captcha_math":   "https://api.azapi.ai/m0001c/1",
    "ocr_generic":    "https://ocr.azapi.ai/g0002d",
    "kyc_india":      "https://ocr.azapi.ai/ind0001d",
    "bank":           "https://ocr.azapi.ai/bank0001d",
    "kyc_overseas":   "https://ocr.azapi.ai/ov0001d",
}


def solve_captcha(image):
    """Solve an image-based captcha (Text-CAPTCHA / math captcha)."""
    return _post(ENDPOINTS["captcha_text"], image)


def ocr_document(image, endpoint="ocr_generic"):
    """OCR a document. endpoint = key from ENDPOINTS or a full URL."""
    url = ENDPOINTS.get(endpoint, endpoint)
    return _post(url, image)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("usage: python azapi.py <endpoint_key|url> <image_path>")
        print("example: python azapi.py ocr_generic receipt.jpg")
        print("endpoints:", ", ".join(ENDPOINTS))
        sys.exit(1)
    ep, img = sys.argv[1], sys.argv[2]
    if ep.startswith("http"):
        print(_post(ep, img))
    else:
        print(ocr_document(img, ep))
