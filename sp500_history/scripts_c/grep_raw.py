import json, sys, re
d = json.load(open(sys.argv[1], encoding='utf-8'))
h = d['rawHtml']
pats = sys.argv[2:]
for p in pats:
    print('=====', p)
    seen=0
    for m in re.finditer(p, h):
        s=max(0,m.start()-250); e=min(len(h), m.end()+250)
        print('---', h[s:e].replace('\n',' '))
        seen+=1
        if seen>=8: break
