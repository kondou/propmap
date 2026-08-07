#!/usr/bin/env python3
"""RBN CSVのutc_day分布を確認"""
import csv, glob, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from contest_utils import msg

csv_dir = Path(__file__).resolve().parent / "csv"
files = sorted(csv_dir.glob("*_rbn_pairs.csv"))

if not files:
    print(msg(f"RBN CSVが見つかりません: {csv_dir}",
              f"No RBN CSV found: {csv_dir}"))
    sys.exit(1)

for fpath in files:
    day_counts = {}
    total = 0
    with open(fpath, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            total += 1
            d = int(row.get("utc_day", 0))
            day_counts[d] = day_counts.get(d, 0) + 1
    print(f"{fpath.name}:")
    print(msg(f"  総行数: {total}", f"  Total rows: {total}"))
    for d in sorted(day_counts):
        print(msg(f"  utc_day={d}: {day_counts[d]}行 ({day_counts[d]/total*100:.1f}%)",
                  f"  utc_day={d}: {day_counts[d]} rows ({day_counts[d]/total*100:.1f}%)"))
