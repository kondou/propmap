#!/usr/bin/env python3
"""
指定条件でqso_pairs.csvから該当レコードを抽出し
QSOペアおよびロケータ別QSO数を表示するデバッグツール
"""
import csv, math, argparse, sys
from pathlib import Path
from collections import defaultdict

RES_MIN = 10  # 固定

def grid4_latlon(g):
    g = g.upper()
    lon = (ord(g[0])-65)*20 - 180 + int(g[2])*2 + 1
    lat = (ord(g[1])-65)*10 - 90  + int(g[3]) + 0.5
    return lat, lon

def gcd_km(lat1, lon1, lat2, lon2):
    R = 6371
    rl = math.radians
    dlat = rl(lat2-lat1); dlon = rl(lon2-lon1)
    a = math.sin(dlat/2)**2 + math.cos(rl(lat1))*math.cos(rl(lat2))*math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))

def main():
    ap = argparse.ArgumentParser(description="QSOペア詳細チェックツール")
    ap.add_argument("--contest", help="コンテスト識別子 (例: cqwpx_cw)")
    ap.add_argument("--year",    type=int, help="開催年 (例: 2024)")
    ap.add_argument("--center",  default="PM52", help="中心グリッドロケータ (デフォルト: PM52)")
    ap.add_argument("--dist-km", type=float, default=250.0, help="中心からの距離km (デフォルト: 250)")
    ap.add_argument("--hour",    type=int, help="UTCアワー (0-23)")
    ap.add_argument("--min",     type=int, help="UTC分 (0,10,20,30,40,50)")
    ap.add_argument("--bands",   nargs="+", default=["40m", "20m"],
                    help="バンド (例: 40m 20m 15m  デフォルト: 40m 20m)")
    args = ap.parse_args()

    if not args.contest:
        args.contest = input("コンテスト識別子 (例: cqwpx_cw): ").strip()
    if args.year is None:
        args.year = int(input("開催年 (例: 2024): ").strip())
    if args.hour is None:
        args.hour = int(input("UTCアワー (0-23): ").strip())
    if args.min is None:
        args.min = int(input("UTC分 (0,10,20,30,40,50): ").strip())

    if args.min % 10 != 0 or not (0 <= args.min <= 50):
        print("エラー: UTC分は 0,10,20,30,40,50 のいずれかで指定")
        sys.exit(1)

    try:
        CY, CX = grid4_latlon(args.center)
    except Exception:
        print(f"エラー: 無効なグリッドロケータ: {args.center}")
        sys.exit(1)

    BANDS  = set(args.bands)
    t_step = (args.hour * 60 + args.min) // RES_MIN

    print(f"コンテスト : {args.contest} {args.year}")
    print(f"中心       : {args.center} (lat={CY}, lon={CX})")
    print(f"距離       : {args.dist_km} km 以内")
    print(f"UTC時刻    : {args.hour:02d}:{args.min:02d}z  t_step={t_step}(Day1) / {t_step+144}(Day2)")
    print(f"バンド     : {', '.join(sorted(BANDS))}")
    print()

    csv_path = Path.home()/"heatmap"/"contest_logs"/"csv"/f"{args.contest}_{args.year}_qso_pairs.csv"
    if not csv_path.exists():
        print(f"エラー: ファイルが見つかりません: {csv_path}")
        sys.exit(1)

    # day -> band -> list of records
    results = {0: defaultdict(list), 1: defaultdict(list)}

    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            band = row["band"]
            if band not in BANDS:
                continue
            utc_day  = int(row.get("utc_day", 0))
            utc_hour = int(row["utc_hour"])
            utc_min  = int(row.get("utc_min", 0))
            row_t    = (utc_day * 1440 + utc_hour * 60 + utc_min) // RES_MIN
            if row_t not in (t_step, t_step + 144):
                continue
            try:
                lat_tx, lon_tx = grid4_latlon(row["grid_tx"][:4])
                dist = gcd_km(CY, CX, lat_tx, lon_tx)
            except Exception:
                continue
            if dist > args.dist_km:
                continue
            results[utc_day][band].append({
                "grid_tx": row["grid_tx"][:4],
                "grid_rx": row["grid_rx"][:4],
                "dist_km": round(dist, 1),
                "power":   row.get("power_tx", ""),
            })

    for day in [0, 1]:
        print(f"{'='*52}")
        print(f"  {args.hour:02d}:{args.min:02d}z  Day{'1' if day==0 else '2'} (utc_day={day})")
        print(f"{'='*52}")
        if not any(results[day].values()):
            print("  (該当なし)")
            print()
            continue
        for band in sorted(BANDS):
            recs = results[day][band]
            print(f"  [{band}]  {len(recs)} ペア")
            for r in recs:
                print(f"    tx={r['grid_tx']}  rx={r['grid_rx']}  dist={r['dist_km']}km  power={r['power']}")
            loc_count = defaultdict(int)
            for r in recs:
                loc_count[r["grid_tx"]] += 1
            print(f"  ロケータ別 ({len(loc_count)} グリッド):")
            for g, n in sorted(loc_count.items(), key=lambda x: -x[1]):
                print(f"    {g}: {n}件")
        print()

if __name__ == "__main__":
    main()
