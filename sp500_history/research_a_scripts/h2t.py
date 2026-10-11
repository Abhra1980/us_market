import re,sys,html
import sys; sys.stdout.reconfigure(encoding="utf-8")
t=open(sys.argv[1],encoding='latin-1').read()
s=re.sub(r'(?is)<script.*?</script>|<style.*?</style>','',t)
s=re.sub(r'(?i)<br\s*/?>|</tr>|</p>|<li>','\n',s)
s=re.sub(r'<[^>]+>',' ',s); s=html.unescape(s)
s=re.sub(r'[ \t\xa0]+',' ',s); s=re.sub(r'\n\s*\n+','\n',s)
n=int(sys.argv[2]) if len(sys.argv)>2 else 4000
print(s[:n])
