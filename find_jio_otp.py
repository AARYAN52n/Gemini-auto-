import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('sample.json', 'r', encoding='utf-8', errors='ignore') as f:
    text = f.read()

jio_otp_sms = re.findall(r'\{[^{}]*"message"[^{}]*(?:Jio|jio|JIO)[^{}]*(?:OTP|otp|code|verification)[^{}]*\}', text)
print(f"Jio OTP SMS found: {len(jio_otp_sms)}")
for s in jio_otp_sms[:10]:
    print("--- Jio OTP SMS ---")
    print(s)
