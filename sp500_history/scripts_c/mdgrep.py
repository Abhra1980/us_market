import json, sys, re
d=json.load(open(sys.argv[1],encoding='utf-8')); md=d['markdown']
meta=d['metadata']; print({k:meta.get(k) for k in ('title','numPages','statusCode','sourceURL')})
w=int(sys.argv[2])
for p in sys.argv[3:]:
    print('=====',p)
    n=0
    for m in re.finditer(p,md,flags=re.I):
        print('---', md[max(0,m.start()-w):m.end()+w].replace('\n',' '))
        n+=1
        if n>=6: break
