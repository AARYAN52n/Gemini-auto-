import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('sample.json', 'r', encoding='utf-8', errors='ignore') as f:
    text = f.read(15000000) # 15MB

for m in re.finditer(r'is OTP|Your OTP|OTP for', text):
    start = max(0, m.start() - 300)
    end = min(len(text), m.end() + 200)
    print("=== MATCH ===")
    print(text[start:end])
    break
