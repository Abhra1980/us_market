import json, sys, re
d = json.load(open(sys.argv[1], encoding='utf-8'))
h = d[sys.argv[2]]
p = sys.argv[3]; w=int(sys.argv[4])
for m in re.finditer(p, h):
    s=max(0,m.start()-w); e=min(len(h), m.end()+w)
    print('---', m.start(), h[s:e].replace('\n',' '))
