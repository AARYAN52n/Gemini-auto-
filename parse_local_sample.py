import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

# sample.json was truncated, but we can fix it or read valid part
with open('sample.json', 'r', encoding='utf-8', errors='ignore') as f:
    text = f.read()

# Let's find the last occurrence of "},"
last_idx = text.rfind('},')
if last_idx != -1:
    fixed_text = text[:last_idx+1] + '}'
    try:
        data = json.loads(fixed_text)
        print(f"Loaded valid JSON! Total keys: {len(data)}")
        
        # Look for device entries
        count = 0
        for k, v in data.items():
            if isinstance(v, dict):
                phone = v.get('phoneNumber') or v.get('phone') or v.get('mobile') or v.get('number')
                sms = v.get('sms')
                if phone or sms:
                    count += 1
                    sms_count = len(sms) if isinstance(sms, dict) else 0
                    print(f"\n--- Node: {k} ---")
                    print(f"Phone: {phone}")
                    print(f"Subkeys: {list(v.keys())}")
                    print(f"SMS count: {sms_count}")
                    if isinstance(sms, dict) and sms:
                        last_sms_key = list(sms.keys())[-1]
                        print(f"Sample SMS ({last_sms_key}): {sms[last_sms_key]}")
                    if count >= 5:
                        break
        print(f"\nTotal nodes with phone/sms inspected: {count}")
    except Exception as e:
        print("Error parsing fixed JSON:", e)
