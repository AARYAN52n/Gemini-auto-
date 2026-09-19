import re
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

# Let's find all occurrences of "phoneNumber", "phone", "number", "sim" etc.
with open('sample.json', 'r', encoding='utf-8', errors='ignore') as f:
    text = f.read()

print("Total text length:", len(text))

# Let's search for what keys exist under users
user_devices = re.findall(r'"users":\{"([0-9a-fA-F]+)":\{([^}]+)\}', text)
print(f"Matched user devices: {len(user_devices)}")
for dev_id, content in user_devices[:5]:
    print(f"Device: {dev_id}")
    print(f"Content: {content[:300]}")

# Let's search where phone numbers are stored across the entire DB
phone_matches = re.findall(r'"([a-zA-Z0-9_]+)":\s*"(\+?91[6-9][0-9]{9}|[6-9][0-9]{9})"', text)
print("\nKeys that hold phone numbers:")
key_counts = {}
for k, p in phone_matches:
    key_counts[k] = key_counts.get(k, 0) + 1
for k, count in sorted(key_counts.items(), key=lambda x: x[1], reverse=True):
    print(f"  {k}: {count} times (e.g. {dict(phone_matches)[k]})")
