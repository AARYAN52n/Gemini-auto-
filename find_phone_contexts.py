import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('sample.json', 'r', encoding='utf-8', errors='ignore') as f:
    text = f.read()

for field in ['phoneNumber', 'number', 'mobile']:
    print(f"\n================ FIELD: {field} ================")
    matches = list(re.finditer(rf'"{field}"\s*:\s*"(\+?91[6-9][0-9]{{9}}|[6-9][0-9]{{9}})"', text))
    print(f"Total found: {len(matches)}")
    for m in matches[:3]:
        start = max(0, m.start() - 200)
        end = min(len(text), m.end() + 200)
        print("--- CONTEXT ---")
        print(text[start:end])
