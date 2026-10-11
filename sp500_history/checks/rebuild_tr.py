"""Rebuild S&P 500 TR from S&P's price export + quarterly dividend points export; compare to S&P's TR export."""
import json, re, sys
from datetime import datetime
from pathlib import Path

root = Path(sys.argv[1])

def series(p):
    md = json.load(open(root / p, encoding="utf-8"))["markdown"]
    out = {}
    for line in md.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%b %d, %Y", "%d-%b-%Y"):
            try:
                d = datetime.strptime(cells[0], fmt).date()
                break
            except ValueError:
                d = None
        if d is None:
            continue
        try:
            out[d] = float(cells[1].replace(",", ""))
        except ValueError:
            pass
    return out

px = series("export_10y/export_10y.json")
tr = series("export_tr10y/export_tr10y.json")
dp = series("export_divpts10y/d.json")
days = sorted(set(px) & set(tr) & set(dp))
print("rows px/tr/dp/common:", len(px), len(tr), len(dp), len(days), days[0], days[-1])

level = tr[days[0]]
worst = 0.0
resets = 0
for a, b in zip(days, days[1:]):
    if dp[b] < dp[a]:
        div = dp[b]
        resets += 1
    else:
        div = dp[b] - dp[a]
    level *= (px[b] + div) / px[a]
    worst = max(worst, abs(level / tr[b] - 1))
print("resets:", resets)
print("rebuilt end %.2f vs official %.2f" % (level, tr[days[-1]]))
print("worst cumulative drift: %.2f bp" % (worst * 1e4))
