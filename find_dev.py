import sys, re
sys.stdout.reconfigure(encoding='utf-8')
with open('sample.json', 'r', encoding='utf-8', errors='ignore') as f:
    text = f.read()

pos = text.find('917696121957')
# Let's find "receivedSms" before pos
r_pos = text.rfind('"receivedSms"', 0, pos)
print('receivedSms pos:', r_pos)
# Let's find the key before receivedSms!
before_rcv = text[:r_pos]
keys_before = list(re.finditer(r'"([0-9a-zA-Z_-]+)":\s*\{', before_rcv))
for m in keys_before[-4:]:
    print('Key:', m.group(1), 'at', m.start())
