import requests
import json

with open("firebase_url.txt", "r", encoding="utf-8") as f:
    lines = [line.strip() for line in f if line.strip()]

for line in lines[:25]:
    parts = line.split()
    url = parts[-1]
    if not url.startswith("http"):
        continue
    db_url = url.rstrip('/') + '/.json'
    try:
        r = requests.get(db_url, timeout=4)
        if r.status_code == 200:
            data = r.json()
            if data:
                print(f"[FOUND DATA] {url}")
                if isinstance(data, dict):
                    print("  Keys:", list(data.keys())[:10])
                    for k in list(data.keys())[:2]:
                        sub = data[k]
                        if isinstance(sub, dict):
                            print(f"    Sample [{k}]:", list(sub.keys())[:5], str(sub)[:150])
                        else:
                            print(f"    Sample [{k}]:", str(sub)[:150])
                else:
                    print("  Data type:", type(data), str(data)[:200])
            else:
                print(f"[EMPTY] {url}")
        else:
            print(f"[{r.status_code}] {url}")
    except Exception as e:
        print(f"[ERR] {url}: {e}")
