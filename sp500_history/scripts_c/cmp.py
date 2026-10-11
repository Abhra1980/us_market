import json, sys, re, math
def load(p):
    md=json.load(open(p,encoding='utf-8'))['markdown']; out={}
    for l in md.splitlines():
        c=[x.strip() for x in l.strip().strip('|').split('|') if x.strip()]
        if c and re.match(r'\d{4}-\d{2}-\d{2}$',c[0]): out[c[0]]=[float(x) for x in c[1:]]
    return out
a=load(sys.argv[1]); b=load(sys.argv[2])
common=sorted(set(a)&set(b)); diff=[(d,a[d],b[d]) for d in common if a[d]!=b[d]]
print('overlap',len(common),common[0],common[-1],'mismatches',len(diff), diff[:5])
if len(sys.argv)>3:
    pr=load(sys.argv[3]); tr=load(sys.argv[4]); ds=sorted(set(pr)&set(tr))
    # implied dividend return per year = TR growth / PR growth
    import collections
    yr=collections.OrderedDict()
    for i in range(1,len(ds)):
        d0,d1=ds[i-1],ds[i]
        r_tr=tr[d1][0]/tr[d0][0]; r_pr=pr[d1][0]/pr[d0][0]
        y=d1[:4]; yr.setdefault(y,[1,1]); yr[y][0]*=r_tr; yr[y][1]*=r_pr
    for y,(t,p) in yr.items(): print(y, 'TR %.2f%% PR %.2f%% gap %.2f%%'%((t-1)*100,(p-1)*100,(t/p-1)*100))
    neg=[(ds[i],tr[ds[i]][0]/tr[ds[i-1]][0]-pr[ds[i]][0]/pr[ds[i-1]][0]) for i in range(1,len(ds))]
    print('days TR ret < PR ret by >1bp:', sum(1 for d,x in neg if x< -1e-4), 'max daily gap %.4f%%'%(max(x for d,x in neg)*100))
