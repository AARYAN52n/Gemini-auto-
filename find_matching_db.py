import json
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('scanned_firebase.json', 'r', encoding='utf-8') as f:
    scanned = json.load(f)

open_dbs = [d['url'] for d in scanned if d['status'] == 'open']
print(f"Checking {len(open_dbs)} open DBs for sample device...", flush=True)

target_dev = '0201eee2417fe7af'
target_phone = '7696121957'

def check(url):
    # Try direct
    try:
        r1 = requests.get(f"{url}/{target_dev}.json?shallow=true", timeout=4)
        if r1.status_code == 200 and r1.json():
            return f"MATCH direct: {url}/{target_dev}"
    except:
        pass
    
    # Try under users
    try:
        r2 = requests.get(f"{url}/users/{target_dev}.json?shallow=true", timeout=4)
        if r2.status_code == 200 and r2.json():
            return f"MATCH users: {url}/users/{target_dev}"
    except:
        pass

    # Try under clients or other
    try:
        r3 = requests.get(f"{url}/All_Users/{target_dev}.json?shallow=true", timeout=4)
        if r3.status_code == 200 and r3.json():
            return f"MATCH All_Users: {url}/All_Users/{target_dev}"
    except:
        pass

    return None

with ThreadPoolExecutor(max_workers=30) as ex:
    futs = {ex.submit(check, u): u for u in open_dbs}
    for f in as_completed(futs):
        res = f.result()
        if res:
            print(">>>", res, flush=True)
print("Done search.", flush=True)
