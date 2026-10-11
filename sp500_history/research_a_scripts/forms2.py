import json, sys, collections, glob, os
cik = sys.argv[1]; d0 = sys.argv[2]
want = set(sys.argv[3].split(','))
out = sys.argv[4] if len(sys.argv)>4 else None
rows = []
def add(r):
    for i in range(len(r['form'])):
        rows.append((r['form'][i], r['filingDate'][i], r['reportDate'][i], r['accessionNumber'][i], r.get('primaryDocument',['']*len(r['form']))[i]))
d = json.load(open(os.path.join(d0, f'CIK{cik}.json')))
add(d['filings']['recent'])
for f in sorted(glob.glob(os.path.join(d0, f'CIK{cik}-submissions-*.json'))):
    add(json.load(open(f)))
c = collections.Counter()
for f, fd, rd, acc, pd in rows:
    if f in want: c[(f, fd[:4])] += 1
for k in sorted(c, key=lambda x:(x[0],x[1])): print(k, c[k])
if out:
    with open(out,'w') as fh:
        for r in sorted(rows, key=lambda x:x[1]):
            if r[0] in want: fh.write('\t'.join(r)+'\n')
