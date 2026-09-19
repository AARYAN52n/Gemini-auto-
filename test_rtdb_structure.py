import requests
import json

def inspect_url(base_url):
    print(f"\n=== INSPECTING: {base_url} ===")
    r = requests.get(base_url.rstrip('/') + '/.json?shallow=true', timeout=5)
    if r.status_code != 200:
        print(f"Failed with status {r.status_code}")
        return
    keys = list(r.json().keys())
    print(f"Top keys ({len(keys)}): {keys[:15]}")
    
    # Check if there are phone numbers or devices
    found_numbers = []
    # Test top 5 keys
    for k in keys[:10]:
        try:
            sub = requests.get(f"{base_url.rstrip('/')}/{k}/.json", timeout=5).json()
            if isinstance(sub, dict):
                # Check for phone number fields
                phone = sub.get('phoneNumber') or sub.get('phone') or sub.get('mobile') or sub.get('number')
                sms = sub.get('sms') or sub.get('messages') or sub.get('all_sms')
                print(f"Key [{k}]: phone={phone}, sms_keys={list(sms.keys())[:3] if isinstance(sms, dict) else type(sms)}")
                if phone:
                    found_numbers.append((k, phone))
        except Exception as e:
            pass
    print("Found numbers:", found_numbers)

# Test a few URLs
inspect_url('https://hood-4ba1e-default-rtdb.firebaseio.com')
inspect_url('https://lucifer-spreader-default-rtdb.firebaseio.com')
inspect_url('https://systumm-c8526-default-rtdb.firebaseio.com')
