#!/usr/bin/env python3
"""RBN JSONの詳細比較（t_step>=144のレコード構造確認）"""
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "contest_logs"))
from contest_utils import msg

data_dir = Path(__file__).resolve().parent / "data"

for fname in sorted(data_dir.glob("*_rbn.json")):
    d = json.load(open(fname))
    recs = d.get("records", [])
    if not recs:
        continue

    recs144 = [r for r in recs if r[3] >= 144]
    if not recs144:
        print(msg(f"{fname.name}: t_step>=144 のレコードなし",
                  f"{fname.name}: no records with t_step>=144"))
        continue

    sample = recs144[0]
    print(f"{fname.name}:")
    print(msg(f"  レコード長: {len(sample)} 要素",
              f"  Record length: {len(sample)} elements"))
    print(msg(f"  サンプル(t_step>=144): {sample}",
              f"  Sample (t_step>=144): {sample}"))
    print(msg(f"  gridsのサンプルキー: {list(d['grids'].keys())[:3]}",
              f"  Sample grid keys: {list(d['grids'].keys())[:3]}"))

    # gridsにrec[0]とrec[4]が存在するか
    found = sum(1 for r in recs144[:1000]
                if r[0] in d['grids'] or r[4] in d['grids'])
    print(msg(f"  grids参照可能(先頭1000件中): {found}/1000",
              f"  Resolvable in grids (first 1000): {found}/1000"))
    print()
