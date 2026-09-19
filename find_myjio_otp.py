import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('sample.json', 'r', encoding='utf-8', errors='ignore') as f:
    text = f.read()

# Search for senders matching JIO
jio_otp_senders = re.findall(r'\{[^{}]*"message"[^{}]*(?:otp|OTP|code)[^{}]*"sender"[^{}]*JIO[^{}]*\}', text, re.IGNORECASE)
print(f"Jio OTP by sender count: {len(jio_otp_senders)}")
for s in jio_otp_senders[:10]:
    print("--- Jio OTP by sender ---")
    print(s)

# Also search for "MyJio" or "verification code"
myjio = re.findall(r'\{[^{}]*"message"[^{}]*(?:MyJio|myjio)[^{}]*\}', text)
print(f"MyJio SMS count: {len(myjio)}")
for s in myjio[:5]:
    print("--- MyJio SMS ---")
    print(s)
