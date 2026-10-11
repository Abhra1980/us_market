import json, sys, re
def load(p):
    md=json.load(open(p,encoding='utf-8'))['markdown']; o={}
    for l in md.splitlines():
        c=[x.strip() for x in l.strip().strip('|').split('|') if x.strip()]
        if c and re.match(r'\d{4}-\d{2}-\d{2}$',c[0]): o[c[0]]=float(c[1])
    return o
pr=load(sys.argv[1]); tr=load(sys.argv[2]); dp=load(sys.argv[3])
ds=sorted(set(pr)&set(tr)&set(dp)); print('common days',len(ds),ds[0],ds[-1])
# daily dividend points: dp_t - dp_{t-1}, or dp_t if reset (dp_t < dp_{t-1})
rec=tr[ds[0]]; errs=[]; resets=0
for a,b in zip(ds,ds[1:]):
    dd=dp[b]-dp[a]
    if dd< -1e-9: dd=dp[b]; resets+=1
    rec=rec*(pr[b]+dd)/pr[a]
    errs.append((b,(rec/tr[b]-1)*1e4))
print('resets detected',resets)
print('final reconstructed %.2f vs official %.2f, drift %.2f bp'%(rec,tr[ds[-1]],errs[-1][1]))
print('max |drift| bp %.2f'%max(abs(e) for d,e in errs))
# day-by-day check without compounding error: implied vs official daily return
bad=0; worst=(None,0)
for a,b in zip(ds,ds[1:]):
    dd=dp[b]-dp[a]
    if dd< -1e-9: dd=dp[b]
    r_imp=(pr[b]+dd)/pr[a]-1; r_off=tr[b]/tr[a]-1
    e=(r_imp-r_off)*1e4
    if abs(e)>1: bad+=1
    if abs(e)>abs(worst[1]): worst=(b,e)
print('days with |daily diff|>1bp',bad,'worst',worst)
