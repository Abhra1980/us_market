import json, sys
d = json.load(open(sys.argv[1], encoding='utf-8'))
md = d['markdown']
print(d['metadata'])
print(len(md))
lines = md.splitlines()
print(len(lines))
for l in lines[:40]: print(l[:300])
print('....')
for l in lines[-15:]: print(l[:300])
