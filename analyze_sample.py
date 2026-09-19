import re
import json

with open('sample.json', 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read(5000000) # first 5MB

matches = re.findall(r'"(?:phoneNumber|phone|mobile|number|simNumber)"\s*:\s*"([^"]+)"', content)
print("Found phone attributes:", set(matches[:25]))

# Also check for device nodes:
# Typical pattern in these SMS forwarders:
# "/<deviceId>/sms/<msgId>/message" or similar
# Let's find some JSON blocks with phoneNumber and sms
device_blocks = re.findall(r'\{[^{}]*"phoneNumber"[^{}]*\}', content)
print(f"Device blocks found: {len(device_blocks)}")
for b in device_blocks[:5]:
    print("Block:", b)

# Let's check SMS patterns
sms_blocks = re.findall(r'\{[^{}]*"message"[^{}]*"sender"[^{}]*\}', content)
print(f"SMS blocks found: {len(sms_blocks)}")
for s in sms_blocks[:5]:
    print("SMS block:", s)
