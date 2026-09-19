import re
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

# Read sample.json
with open('sample.json', 'r', encoding='utf-8', errors='ignore') as f:
    text = f.read()

# Let's find all occurrences of receivedSms and find the parent device and phone number
pattern = re.compile(r'"([0-9a-fA-F]{16})":\s*\{[^}]*?"receivedSms"', re.DOTALL)

# Let's search by scanning JSON objects or regex for "receivedSms"
print("Scanning for receivedSms...")
matches = list(re.finditer(r'"receivedSms":\s*\{', text))
print(f"Total receivedSms blocks found: {len(matches)}")

devices_found = []
for m in matches:
    # Look backwards for device ID and simInfo/phoneNumber/mobile
    start = max(0, m.start() - 2500)
    end = min(len(text), m.end() + 2500)
    chunk = text[start:end]
    
    # Check for phone numbers in chunk
    phones = re.findall(r'"(?:number|mobile|phoneNumber)":\s*"(\+?91[6-9][0-9]{9}|[6-9][0-9]{9})"', chunk)
    # Check for device id (16 hex)
    dev_ids = re.findall(r'"([0-9a-fA-F]{16})":\s*\{', chunk)
    
    # Check carrier
    carrier = re.findall(r'"carrierName":\s*"([^"]+)"', chunk)
    
    if phones:
        clean_phone = phones[0][-10:] # last 10 digits
        devices_found.append({
            'phone': clean_phone,
            'carrier': carrier[0] if carrier else 'Unknown',
            'dev_id': dev_ids[0] if dev_ids else 'Unknown',
            'pos': m.start()
        })

print(f"Found {len(devices_found)} devices with phone and receivedSms:")
for d in devices_found[:15]:
    print(" ", d)
