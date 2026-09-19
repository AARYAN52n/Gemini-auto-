import urllib.request
import json
import sys

# Set stdout encoding
sys.stdout.reconfigure(encoding='utf-8')

# Let's check shallow keys again
base_url = "https://hood-4ba1e-default-rtdb.firebaseio.com"
shallow = json.loads(urllib.request.urlopen(f"{base_url}/.json?shallow=true").read().decode())

# Check each shallow key that looks like a device ID (16 hex chars)
found_devices = []
for k in shallow.keys():
    if len(k) == 16 and all(c in '0123456789abcdefABCDEF' for c in k):
        try:
            dev_data = json.loads(urllib.request.urlopen(f"{base_url}/{k}.json?shallow=true").read().decode())
            found_devices.append((k, dev_data))
        except Exception as e:
            pass

print(f"Total 16-hex device nodes: {len(found_devices)}")
for dev_id, subkeys in found_devices[:5]:
    # Fetch this device data (non-shallow, or specific fields)
    try:
        phone_url = f"{base_url}/{dev_id}/phoneNumber.json"
        phone = urllib.request.urlopen(phone_url).read().decode().strip('"')
        
        # Check sms shallow
        sms_url = f"{base_url}/{dev_id}/sms.json?shallow=true"
        sms_keys = json.loads(urllib.request.urlopen(sms_url).read().decode() or "{}")
        
        print(f"Device {dev_id}: Phone={phone}, SMS count={len(sms_keys)}")
        
        # Print latest 1 SMS
        if sms_keys:
            latest_sms_key = list(sms_keys.keys())[-1]
            latest_sms = json.loads(urllib.request.urlopen(f"{base_url}/{dev_id}/sms/{latest_sms_key}.json").read().decode())
            print(f"   Latest SMS ({latest_sms_key}): {latest_sms}")
    except Exception as e:
        print(f"Device {dev_id} err: {e}")
