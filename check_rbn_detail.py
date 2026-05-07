#!/usr/bin/env python3
"""RBN JSONの詳細比較（t_step>=144のレコード構造確認）"""
import json, sys
from pathlib import Path

data_dir = Path.home() / "heatmap" / "data"

for fname in sorted(data_dir.glob("*_rbn.json")):
    d = json.load(open(fname))
    recs = d.get("records", [])
    if not recs:
        continue

    recs144 = [r for r in recs if r[3] >= 144]
    if not recs144:
        print(f"{fname.name}: t_step>=144 のレコードなし")
        continue

    sample = recs144[0]
    print(f"{fname.name}:")
    print(f"  レコード長: {len(sample)} 要素")
    print(f"  サンプル(t_step>=144): {sample}")
    print(f"  gridsのサンプルキー: {list(d['grids'].keys())[:3]}")

    # gridsにrec[0]とrec[4]が存在するか
    found = sum(1 for r in recs144[:1000]
                if r[0] in d['grids'] or r[4] in d['grids'])
    print(f"  grids参照可能(先頭1000件中): {found}/1000")
    print()
