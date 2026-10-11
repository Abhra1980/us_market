import json, sys
d = json.load(open(sys.argv[1], encoding='utf-8'))
h = d['rawHtml']
i = h.find(sys.argv[2])
print(h[max(0,i-int(sys.argv[3])): i+int(sys.argv[4])])
