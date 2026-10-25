import time
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
import urllib.parse
import json
import base64
from Crypto.Cipher import AES

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

AUTH_API = "https://auth.platorelay.com/api"
MIN_TICKET_LEN = 33
FALLBACK_VERSION = "5.4.0"
FALLBACK_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"

cache = {}

def aes_ctr_encrypt(data, key, iv):
    cipher = AES.new(bytes(key), AES.MODE_CTR, nonce=b'', initial_value=bytes(iv))
    return cipher.encrypt(data)

def build_meta_stream(ticket, now_ms, user_agent):
    if len(ticket) < MIN_TICKET_LEN:
        return None
    key_meta, ctr_meta = ticket[:16], ticket[16:32]
    key_stream, ctr_stream = ticket[1:17], ticket[17:33]
    
    meta_plain = json.dumps({"browserInfo": [{"screen": "390x844", "ua": user_agent, "time": now_ms}]}, separators=(',', ':')).encode()
    stream_plain = json.dumps({"events": [{"event": 1, "data": {"time": now_ms}}]}, separators=(',', ':')).encode()
    
    meta = aes_ctr_encrypt(meta_plain, [ord(c) for c in key_meta], [ord(c) for c in ctr_meta]).hex()
    stream = aes_ctr_encrypt(stream_plain, [ord(c) for c in key_stream], [ord(c) for c in ctr_stream]).hex()
    return meta, stream

def extract_ticket(url):
    if url.startswith('http'):
        parsed = urllib.parse.urlparse(url)
        qs = urllib.parse.parse_qs(parsed.query)
        if 'd' in qs:
            return qs['d'][0]
    return url.strip()

def do_step(ticket, service=3):
    now_ms = int(time.time() * 1000)
    built = build_meta_stream(ticket, now_ms, FALLBACK_UA)
    if not built:
        return {"error": "Ticket too short"}
    meta, stream = built
    
    url = f"{AUTH_API}/session/step?ticket={urllib.parse.quote(ticket)}&service={service}"
    headers = {
        'User-Agent': FALLBACK_UA,
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'x-client-name': 'platoboost webclient',
        'x-client-version': FALLBACK_VERSION
    }
    body = json.dumps({"captcha": None, "meta": meta, "stream": stream, "resolved": True})
    try:
        r = requests.put(url, data=body, headers=headers, timeout=10)
        return r.json()
    except Exception as e:
        return {"error": str(e)}

def get_session_status(ticket):
    url = f"{AUTH_API}/session/status?ticket={urllib.parse.quote(ticket)}"
    headers = {'User-Agent': FALLBACK_UA, 'Accept': 'application/json'}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        return r.json()
    except Exception as e:
        return {"error": str(e)}

def decode_callback_url(loot_url):
    parsed = urllib.parse.urlparse(loot_url)
    qs = urllib.parse.parse_qs(parsed.query)
    r_param = qs.get('r', [''])[0]
    if not r_param:
        return None
    b64 = r_param.replace('-', '+').replace('_', '/')
    padding = '=' * (4 - len(b64) % 4)
    try:
        dec = base64.b64decode(b64 + padding).decode('utf-8')
        return dec
    except:
        return None

@app.get("/delta")
def get_delta_key(url: str):
    if not url or "auth.platorelay.com" not in url:
        return {"error": "Invalid Platorelay URL"}

    if url in cache:
        if time.time() - cache[url]['time'] < 3600:
            return {"key": cache[url]['key'], "cached": True, "times": "0s"}

    start_time = time.time()
    current_ticket = extract_ticket(url)
    
    if len(current_ticket) < MIN_TICKET_LEN:
        return {"error": "Invalid ticket length"}

    for round_idx in range(6): # Max rounds
        # Check if key already exists
        stat_res = get_session_status(current_ticket)
        data = stat_res.get('data', stat_res) if isinstance(stat_res, dict) else {}
        if data.get('key') and data.get('key') != 'KEY_NOT_FOUND':
            key = data['key']
            cache[url] = {'key': key, 'time': time.time()}
            return {"key": key, "cached": False, "times": f"{round(time.time() - start_time, 1)}s"}

        # Advance checkpoint
        step_res = do_step(current_ticket)
        if step_res.get('error'):
            return {"error": f"Step failed: {step_res['error']}"}
            
        resp_data = step_res.get('data', {})
        next_url = resp_data.get('url', '')
        
        if not next_url:
            return {"error": "No URL in response"}
            
        if next_url == 'about:blank':
            # Poll for key
            for _ in range(15):
                time.sleep(0.5)
                poll_res = get_session_status(current_ticket)
                poll_data = poll_res.get('data', poll_res) if isinstance(poll_res, dict) else {}
                if poll_data.get('key') and poll_data.get('key') != 'KEY_NOT_FOUND':
                    key = poll_data['key']
                    cache[url] = {'key': key, 'time': time.time()}
                    return {"key": key, "cached": False, "times": f"{round(time.time() - start_time, 1)}s"}
            return {"error": "Polling timed out"}

        # Decode callback and get next ticket
        callback = decode_callback_url(next_url)
        if callback:
            parsed_cb = urllib.parse.urlparse(callback)
            qs_cb = urllib.parse.parse_qs(parsed_cb.query)
            if 'd' in qs_cb:
                current_ticket = qs_cb['d'][0]
                continue # Go to next round
        
        return {"error": "Could not decode callback"}

    return {"error": "Max rounds reached without key"}
