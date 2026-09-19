import requests
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open("firebase_url.txt", "r", encoding="utf-8") as f:
    lines = [line.strip() for line in f if line.strip()]

urls = []
for line in lines:
    parts = line.split()
    url = parts[-1]
    if url.startswith("http"):
        urls.append(url)

print(f"Total URLs in file: {len(urls)}")

def test_url(u):
    base = u.rstrip('/')
    print(f"\n================ Testing: {base} ================")
    try:
        r = requests.get(f"{base}/.json?shallow=true", timeout=4)
        if r.status_code != 200:
            print(f"Status: {r.status_code}")
            return
        keys = list(r.json().keys())
        print(f"Shallow keys ({len(keys)}): {keys[:10]}")
        
        # Check if 'users' exists
        if 'users' in keys:
            u_r = requests.get(f"{base}/users/.json?shallow=true", timeout=4)
            if u_r.status_code == 200:
                user_devices = list(u_r.json().keys())
                print(f"  Found 'users' path with {len(user_devices)} devices: {user_devices[:5]}")
                # check one device
                if user_devices:
                    sample_dev = requests.get(f"{base}/users/{user_devices[0]}.json?shallow=true", timeout=4).json()
                    print(f"  Device {user_devices[0]} keys: {list(sample_dev.keys()) if isinstance(sample_dev, dict) else sample_dev}")
                    
        # Check if direct 16-hex device IDs or other common keys
        direct_devs = [k for k in keys if len(k) == 16 and all(c in '0123456789abcdefABCDEF' for c in k)]
        if direct_devs:
            print(f"  Found direct hex device keys ({len(direct_devs)}): {direct_devs[:5]}")
            sample = requests.get(f"{base}/{direct_devs[0]}.json?shallow=true", timeout=4).json()
            print(f"  Direct device sample keys: {list(sample.keys()) if isinstance(sample, dict) else sample}")
            
    except Exception as e:
        print(f"Err: {e}")

# Test first 8 URLs
for u in urls[:8]:
    test_url(u)
