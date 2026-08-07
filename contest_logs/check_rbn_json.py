#!/usr/bin/env python3
"""RBN JSONのt_step分布を確認するスクリプト"""
import json, sys, glob
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from contest_utils import msg

data_dir = Path(__file__).resolve().parent.parent / "data"
pattern = str(data_dir / "*_rbn.json")
files = sorted(glob.glob(pattern))

if not files:
    print(msg(f"RBN JSONが見つかりません: {pattern}",
              f"No RBN JSON found: {pattern}"))
    sys.exit(1)

for fpath in files:
    d = json.load(open(fpath))
    if not d.get("records"):
        print(msg(f"{Path(fpath).name}: レコードなし",
                  f"{Path(fpath).name}: no records"))
        continue
    steps = [r[3] for r in d["records"]]
    print(f"{Path(fpath).name}:")
    print(msg(f"  t_step min={min(steps)} max={max(steps)} レコード数={len(steps)}",
              f"  t_step min={min(steps)} max={max(steps)} records={len(steps)}"))
    print(f"  steps_per_day={d['meta'].get('steps_per_day')} time_resolution_min={d['meta'].get('time_resolution_min')}")
    over144 = sum(1 for s in steps if s >= 144)
    print(msg(f"  t_step>=144のレコード数: {over144} ({over144/len(steps)*100:.1f}%)",
              f"  Records with t_step>=144: {over144} ({over144/len(steps)*100:.1f}%)"))
