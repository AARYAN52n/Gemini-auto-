import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('sample.json', 'r', encoding='utf-8', errors='ignore') as f:
    text = f.read()

# Let's search for "Jio" or "jio" in SMS messages
jio_sms = re.findall(r'\{[^{}]*"message"[^{}]*(?:Jio|jio|JIO)[^{}]*\}', text)
print(f"Jio SMS found: {len(jio_sms)}")
for s in jio_sms[:8]:
    print("--- Jio SMS ---")
    print(s)
