import json, sys, re, datetime as dt
y=json.load(open(sys.argv[1],encoding='utf-8'))['chart']['result'][0]
ts=y['timestamp']; q=y['indicators']['quote'][0]; c=q['close']
print('meta first', dt.datetime.utcfromtimestamp(y['meta']['firstTradeDate']), y['meta'].get('longName'))
off=y['meta']['gmtoffset']
ser={}
for t,v in zip(ts,c):
    d=(dt.datetime.utcfromtimestamp(t+off)).strftime('%Y-%m-%d')
    ser[d]=v
ds=sorted(ser); print('n',len(ds),'first',ds[0],ser[ds[0]],'last',ds[-1],ser[ds[-1]])
nulls=[d for d in ds if ser[d] is None]; print('null closes',len(nulls),nulls[:10])
# gaps > 5 calendar days
gaps=[]
for a,b in zip(ds,ds[1:]):
    g=(dt.date.fromisoformat(b)-dt.date.fromisoformat(a)).days
    if g>5: gaps.append((a,b,g))
print('gaps>5d',len(gaps),gaps[:20])
# big daily moves
mv=[]
prev=None
for d in ds:
    v=ser[d]
    if v is None: continue
    if prev and prev[1]: 
        r=v/prev[1]-1
        if abs(r)>0.08: mv.append((d,round(r*100,2)))
    prev=(d,v)
print('|ret|>8%',mv[:30])
# compare to S&P export
md=json.load(open(sys.argv[2],encoding='utf-8'))['markdown']; sp={}
for l in md.splitlines():
    cc=[x.strip() for x in l.strip().strip('|').split('|') if x.strip()]
    if cc and re.match(r'\d{4}-\d{2}-\d{2}$',cc[0]): sp[cc[0]]=float(cc[1])
com=sorted(set(sp)&set(ser)); 
mis=[(d,sp[d],ser[d]) for d in com if ser[d] is None or abs(sp[d]-ser[d])>0.006]
print('overlap with S&P TR export',len(com),'mismatch >0.005',len(mis),mis[:10])
print('S&P dates missing in Yahoo',[d for d in sorted(sp) if d not in ser][:20])
print('Yahoo dates (in S&P window) missing in S&P',[d for d in ds if d>=min(sp) and d not in sp][:20])
for d in ds[:5]: print(d, ser[d])
