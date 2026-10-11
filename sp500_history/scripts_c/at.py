import json, sys
d = json.load(open(sys.argv[1], encoding='utf-8'))
h = d[sys.argv[2]]
a=int(sys.argv[3]); b=int(sys.argv[4])
print(h[a:b])
