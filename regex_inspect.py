import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('sample.json', 'r', encoding='utf-8', errors='ignore') as f:
    text = f.read(5000000)

# Find top-level keys before ":{"
# Top level keys match: "([a-zA-Z0-9_-]+)":\s*\{
# Let's search for lines or chunks that start with "key":{"phoneNumber"
matches = re.findall(r'"([a-zA-Z0-9_-]{10,40})"\s*:\s*\{([^\{\}]+(?:\{[^\}]+\}[^\{\}]*)*)\}', text)
print(f"Regex matched objects: {len(matches)}")

# Let's specifically search for phoneNumber
phones = re.findall(r'"phoneNumber"\s*:\s*"([0-9+]{10,15})"', text)
print(f"Unique phone numbers in first 5MB: {len(set(phones))}")
print(list(set(phones))[:15])

# Let's find what fields are nearby phoneNumber
for m in re.finditer(r'"phoneNumber"\s*:\s*"([0-9+]{10,15})"', text):
    start = max(0, m.start() - 100)
    end = min(len(text), m.end() + 300)
    print("\n--- Snippet around phoneNumber ---")
    print(text[start:end])
    break

# Let's find how sms messages look like
for m in re.finditer(r'"message"\s*:\s*"([^"]{20,100})"', text):
    start = max(0, m.start() - 100)
    end = min(len(text), m.end() + 200)
    print("\n--- Snippet around message ---")
    print(text[start:end])
    break
