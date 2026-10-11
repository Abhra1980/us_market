import json, sys, re
rows = json.load(open(sys.argv[1], encoding='utf-8'))[1:]
print('total captures', len(rows))
ids = set(sys.argv[2].split(','))
hits=[]
for ts, url, st, mt, ln in rows:
    u = url.replace('&amp;','&')
    m = re.findall(r'indexId=(\d+)', u)
    if any(x in ids for x in m) and 'Performance' in u:
        hits.append((ts, st, mt, ln, u))
hits.sort()
for h in hits: print(h)
