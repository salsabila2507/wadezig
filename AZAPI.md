# AZAPI (GMI Cloud API)

Document / OCR & captcha-solving API for GMI Cloud. Client: `azapi.py`.

## Auth
```
Authorization: <AZAPI_KEY>      # no "Bearer" prefix
Content-Type: image/jpeg        # body = raw image bytes
```
Set the key via env var `AZAPI_KEY`, or a local `.env` file (`AZAPI_KEY=...`).
A `.env.example` is provided — copy it to `.env` and fill your key. `.env` is gitignored.

## Base URLs
| Host | Purpose | Example endpoints |
|------|---------|------------------|
| `https://api.azapi.ai` | CAPTCHA solver | `t0001c` (text), `m0001c/1` (math) |
| `https://ocr.azapi.ai` | OCR / KYC / Bank | `g0002d` (generic), `ind0001d` (KYC India), `bank0001d`, `ov0001d` (overseas) |

## Usage (Python)
```python
from azapi import solve_captcha, ocr_document, ENDPOINTS

# solve an image captcha
status, resp = solve_captcha("captcha.png")
print(resp["output"])            # {"captcha": "...", "captcha_type": "Text-CAPTCHA"}

# OCR a document
status, resp = ocr_document("receipt.jpg", "ocr_generic")
print(resp["output"])            # extracted fields
```

## CLI
```bash
python azapi.py ocr_generic receipt.jpg
python azapi.py https://ocr.azapi.ai/ind0001d id.jpg
```

## Notes
- Responses are JSON: `{"status":"Success","billable":"Yes","output":{...}, ...}`.
- `billable: "Yes"` even on the sandbox key — calls are real.
- Endpoints that need a document upload return `{"errors":{"document":"Document not uploaded..."}}`
  if the body isn't a valid image.
- This is the API access route for GMI; the console web signup is gated by reCAPTCHA v3
  and is not automatable from this environment.
