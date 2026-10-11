import json, sys, collections
p = sys.argv[1]
d = json.load(open(p))
print(d.get('name'), d.get('cik'), 'formerNames', d.get('formerNames'))
rows = []
def add(r):
    for i in range(len(r['form'])):
        rows.append((r['form'][i], r['filingDate'][i], r['reportDate'][i], r['accessionNumber'][i], r.get('primaryDocument',[''])[i]))
add(d['filings']['recent'])
print('extra files', [f['name'] for f in d['filings'].get('files',[])])
want = set(sys.argv[2].split(',')) if len(sys.argv)>2 else None
c = collections.Counter()
for f, fd, rd, acc, pd in rows:
    if want and f not in want: continue
    c[(f, fd[:4])] += 1
for k in sorted(c, key=lambda x:(x[0],x[1])):
    print(k, c[k])
print('earliest in recent', min(r[1] for r in rows))
