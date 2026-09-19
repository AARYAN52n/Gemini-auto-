import re
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('sample.json', 'r', encoding='utf-8', errors='ignore') as f:
    text = f.read(30000000)

users_pos = text.find('"users":{')
if users_pos != -1:
    print("Found 'users' key!")
    snippet = text[users_pos:users_pos+5000]
    print(snippet[:1500])
else:
    print("'users' key not found")
