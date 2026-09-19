import json
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('scanned_firebase.json', 'r', encoding='utf-8') as f:
    scanned = json.load(f)

open_dbs = [d['url'] for d in scanned if d['status'] == 'open']
print(f"Classifying schemas across {len(open_dbs)} open DBs...", flush=True)

def classify_db(url):
    info = {
        'url': url,
        'has_admin_users': False,
        'has_root_devices': False,
        'has_numbers_node': False,
        'has_users_devices': False,
        'has_messages_node': False,
        'sample_numbers': [],
        'device_count': 0
    }
    try:
        r = requests.get(f"{url}/.json?shallow=true", timeout=4)
        if r.status_code != 200:
            return info
        keys = set(r.json().keys())
        
        # 1. Admin users (like PMADMIN...)
        if 'admin' in keys:
            try:
                adm = requests.get(f"{url}/admin.json?shallow=true", timeout=3).json()
                if isinstance(adm, dict):
                    for a in list(adm.keys())[:3]:
                        u = requests.get(f"{url}/admin/{a}/users.json?shallow=true", timeout=3).json()
                        if isinstance(u, dict) and u:
                            info['has_admin_users'] = True
                            info['device_count'] += len(u)
            except:
                pass

        # 2. numbers node (like +9198...)
        if 'numbers' in keys:
            try:
                nums = requests.get(f"{url}/numbers.json?shallow=true", timeout=3).json()
                if isinstance(nums, dict) and nums:
                    info['has_numbers_node'] = True
                    info['sample_numbers'] = list(nums.keys())[:5]
                    info['device_count'] += len(nums)
            except:
                pass

        # 3. users node (direct device IDs or push IDs)
        if 'users' in keys:
            try:
                usr = requests.get(f"{url}/users.json?shallow=true", timeout=3).json()
                if isinstance(usr, dict) and usr:
                    info['has_users_devices'] = True
                    info['device_count'] += len(usr)
            except:
                pass

        # 4. messages node
        if 'messages' in keys:
            info['has_messages_node'] = True

        # 5. Direct hex devices at root
        hex_devs = [k for k in keys if len(k) == 16 and all(c in '0123456789abcdefABCDEF' for c in k)]
        if hex_devs:
            info['has_root_devices'] = True
            info['device_count'] += len(hex_devs)

    except:
        pass
    return info

classified = []
with ThreadPoolExecutor(max_workers=25) as ex:
    futs = {ex.submit(classify_db, u): u for u in open_dbs}
    for f in as_completed(futs):
        res = f.result()
        classified.append(res)
        features = []
        if res['has_admin_users']: features.append('admin_users')
        if res['has_numbers_node']: features.append(f"numbers({len(res['sample_numbers'])}+)")
        if res['has_users_devices']: features.append('users_devices')
        if res['has_root_devices']: features.append('root_devices')
        if res['has_messages_node']: features.append('messages')
        print(f"DB: {res['url']} -> Devices: {res['device_count']} | Features: {', '.join(features)}", flush=True)

with open('classified_dbs.json', 'w', encoding='utf-8') as f:
    json.dump(classified, f, indent=2)
print("Saved classified_dbs.json", flush=True)
