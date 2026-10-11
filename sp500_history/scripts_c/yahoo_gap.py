import json, sys, datetime as dt
def ys(p):
    y=json.load(open(p,encoding='utf-8'))['chart']['result'][0]; off=y['meta']['gmtoffset']
    return {(dt.datetime(1970,1,1)+dt.timedelta(seconds=t+off)).strftime('%Y-%m-%d'):v for t,v in zip(y['timestamp'],y['indicators']['quote'][0]['close']) if v is not None}
tr=ys(sys.argv[1]); pr=ys(sys.argv[2])
print('GSPC first',min(pr),pr[min(pr)],'n',len(pr))
ds=sorted(set(tr)&set(pr)); print('common',len(ds), 'TR-only', len(set(tr)-set(pr)), 'PR-only after 1988', len([d for d in pr if d>='1988-01-04' and d not in tr]))
bad=[]
for a,b in zip(ds,ds[1:]):
    g=(tr[b]/tr[a])-(pr[b]/pr[a])
    if g< -0.0005 or g>0.003: bad.append((b,round(g*100,3)))
print('days with TR-PR gap < -5bp or > 30bp:',len(bad)); print(bad[:60])
for d in ['2019-03-11','2019-03-12','2019-03-13','2019-07-02','2019-07-03','2019-07-05']: print(d, tr.get(d), pr.get(d))
