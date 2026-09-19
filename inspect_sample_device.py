import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('sample.json', 'r', encoding='utf-8', errors='ignore') as f:
    text = f.read()

target = '033701af628357fe'
pos = text.find(target)
print('Pos:', pos)
print(text[pos-50:pos+1500])
