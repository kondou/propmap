#!/usr/bin/env python3
"""RBN CSVのutc_day分布を確認"""
import csv, glob, sys
from pathlib import Path

csv_dir = Path.home() / "heatmap" / "contest_logs" / "csv"
files = sorted(csv_dir.glob("*_rbn_pairs.csv"))

if not files:
    print(f"RBN CSVが見つかりません: {csv_dir}")
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
    print(f"  総行数: {total}")
    for d in sorted(day_counts):
        print(f"  utc_day={d}: {day_counts[d]}行 ({day_counts[d]/total*100:.1f}%)")
