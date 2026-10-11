import json, sys, re
d = json.load(open(sys.argv[1], encoding='utf-8'))
md = d['markdown']
rows=[]; other=[]
for l in md.splitlines():
    cells=[c.strip() for c in l.strip().strip('|').split('|')]
    ne=[c for c in cells if c]
    if not ne or set(''.join(cells))<=set('- '): continue
    if re.match(r'\d{4}-\d{2}-\d{2}$', ne[0]): rows.append(ne)
    else: other.append(ne)
print(d['metadata'].get('statusCode'), d['metadata'].get('contentType'))
print('n rows', len(rows))
if rows:
    print('first', rows[0], 'last', rows[-1])
    from collections import Counter
    print('col counts', Counter(len(r) for r in rows))
for o in other:
    print('OTHER', [x[:120] for x in o[:6]])
