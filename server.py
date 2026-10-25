from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import requests
import time
from urllib.parse import urlparse, parse_qs

app = FastAPI()

# Allow your local website to talk to this server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Simple cache so we don't spam the API
cache = {}

@app.get("/delta")
def get_delta_key(url: str):
    if not url or "auth.platorelay.com" not in url:
        return {"error": "Invalid Platorelay URL"}
    
    # Check cache
    if url in cache:
        if time.time() - cache[url]['time'] < 3600: # 1 hour cache
            return {"key": cache[url]['key'], "cached": True, "times": "0s"}

    start_time = time.time()
    
    try:
        # Here is the logic that contacts Platorelay. 
        # Since bypassing changes often, we use a simple placeholder logic.
        # If you have the specific bypass API, you would call it here.
        
        # --- SIMULATED BYPASS FOR DEMONSTRATION ---
        # Real bypassers usually POST the "d" parameter to a checkpoint API.
        parsed_url = urlparse(url)
        ticket = parse_qs(parsed_url.query).get('d', [''])[0]
        
        if not ticket:
            return {"error": "No ticket found in URL"}
            
        # Simulate solving delay
        time.sleep(5)
        
        # Generate a mock key based on the ticket
        mock_key = f"FREE_{ticket[:16]}..."
        
        # Save to cache
        cache[url] = {'key': mock_key, 'time': time.time()}
        
        elapsed = round(time.time() - start_time, 1)
        return {"key": mock_key, "cached": False, "times": f"{elapsed}s"}
        
    except Exception as e:
        return {"error": str(e)}
