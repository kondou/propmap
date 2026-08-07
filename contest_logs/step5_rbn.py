#!/usr/bin/env python3
"""
Step 5 RBN: rbn_pairs.csv → {contest}_{year}_rbn.json への集約

使い方:
  python3 step5_rbn.py --contest iaru --year 2025
  python3 step5_rbn.py --contest cqww_cw --year 2024 --time-resolution 10
"""

import csv, json, argparse, sys
from pathlib import Path
from collections import defaultdict

# ---- i18n -------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent))
try:
    from contest_utils import msg
except ImportError:
    import locale as _lc, os as _os
    def _dlang():
        for v in [_os.environ.get(e, '') for e in ('LANG', 'LC_ALL', 'LANGUAGE')]:
            if v: return 'ja' if v.lower().startswith('ja') else 'en'
        if sys.platform == 'win32':
            # 「地域の形式」ではなくOSの表示言語(UI言語)で判定する
            try:
                import ctypes
                lid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
                return 'ja' if (lid & 0x3FF) == 0x11 else 'en'
            except Exception:
                return 'en'
        try:
            _lc.setlocale(_lc.LC_ALL, '')
            lc = _lc.getlocale()[0] or ''
            if lc.lower().startswith('ja'): return 'ja'
        except Exception: pass
        return 'en'
    _L = _dlang()
    def msg(ja, en=''): return ja if _L == 'ja' else (en or ja)
# -----------------------------------------------------------------------------

BAND_CODE  = {"160m":1,"80m":2,"40m":3,"20m":4,"15m":5,"10m":6}
MODE_CODE  = {"CW":1,"SSB":2,"DIGI":3}
POWER_CODE = {"QRP":1,"LOW":2,"HIGH":3}

def grid4_center(g):
    g = g.upper()
    lon = (ord(g[0])-65)*20-180 + int(g[2])*2+1
    lat = (ord(g[1])-65)*10-90  + int(g[3])+0.5
    return round(lat,1), round(lon,1)

def main():
    ap = argparse.ArgumentParser(
        description=msg("RBNペアCSV → ヒートマップJSON",
                        "RBN pair CSV → heatmap JSON"))
    ap.add_argument("--contest", required=True,
                    help=msg("コンテスト識別子 例: iaru, cqww_cw",
                             "Contest ID e.g.: iaru, cqww_cw"))
    ap.add_argument("--year", type=int, required=True,
                    help=msg("開催年 例: 2025", "Contest year e.g.: 2025"))
    ap.add_argument("--input", nargs="+", default=None,
                    help=msg("入力CSVファイル (省略時: ~/heatmap/contest_logs/csv/{contest}_{year}_rbn_pairs.csv)",
                             "Input CSV file (default: ~/heatmap/contest_logs/csv/{contest}_{year}_rbn_pairs.csv)"))
    ap.add_argument("--output", default=None,
                    help=msg("出力JSONファイル (省略時: ~/heatmap/data/{contest}_{year}_rbn.json)",
                             "Output JSON file (default: ~/heatmap/data/{contest}_{year}_rbn.json)"))
    ap.add_argument("--time-resolution", type=int, default=10,
                    help=msg("時間解像度（分）デフォルト: 10",
                             "Time resolution in minutes (default: 10)"))
    args = ap.parse_args()

    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from contest_utils import validate_contest, rbn_pairs_csv, rbn_json, CONTEST_CFG
        validate_contest(args.contest)
        if not CONTEST_CFG[args.contest]["has_rbn"]:
            print(msg(f"情報: {args.contest} はRBNデータなし（SSBコンテスト）。スキップします。",
                      f"Info: {args.contest} has no RBN data (SSB contest). Skipping."))
            return
        _in  = [rbn_pairs_csv(args.contest, args.year)]
        _out = rbn_json(args.contest, args.year)
    except (ImportError, ValueError) as e:
        cid = f"{args.contest}_{args.year}"
        _script_dir = Path(__file__).resolve().parent
        _in  = [_script_dir/"csv"/f"{cid}_rbn_pairs.csv"]
        _out = _script_dir.parent/"data"/f"{cid}_rbn.json"

    inputs = [Path(p) for p in args.input] if args.input else _in
    out    = Path(args.output) if args.output else _out

    res_min       = args.time_resolution
    steps_per_day = 24*60//res_min

    grid_meta = {}
    agg       = defaultdict(int)
    total_rows = 0

    for csv_path in inputs:
        print(msg(f"読み込み: {csv_path}", f"Loading: {csv_path}"))
        with open(csv_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        print(f"  {len(rows)} " + msg("行", "rows"))
        total_rows += len(rows)

        for p in rows:
            tx4 = p["grid_tx"][:4].upper()
            rx4 = p["grid_rx"][:4].upper()
            try:
                lat_tx, lon_tx = grid4_center(tx4)
                lat_rx, lon_rx = grid4_center(rx4)
            except Exception:
                continue

            if tx4 not in grid_meta:
                grid_meta[tx4] = {"lat": lat_tx, "lon": lon_tx}
            if rx4 not in grid_meta:
                grid_meta[rx4] = {"lat": lat_rx, "lon": lon_rx}

            b  = BAND_CODE.get(p["band"], 0)
            m  = MODE_CODE.get(p.get("mode","CW"), 1)
            pw = POWER_CODE.get(p.get("power_tx","").upper(), 0)

            utc_min = int(p.get("utc_min", 0))
            utc_day = int(p.get("utc_day", 0))
            t_step  = (utc_day * 1440 + int(p["utc_hour"])*60 + utc_min) // res_min

            try:
                sc = int(p.get("spotter_count", 1))
            except (ValueError, TypeError):
                sc = 1

            agg[(rx4, b, m, t_step, tx4, pw)] += sc

    records   = [[k[0],k[1],k[2],k[3],k[4],v,k[5]] for k,v in agg.items()]
    max_count = max((v for v in agg.values()), default=1)

    meta = {
        "time_resolution_min": res_min,
        "steps_per_day":       steps_per_day,
        "max_count_per_cell":  max_count,
        "data_type":           "rbn",
        "power_codes":         {"0":"UNKNOWN","1":"QRP","2":"LOW","3":"HIGH"},
    }

    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump({"meta": meta, "grids": grid_meta, "records": records},
                  f, separators=(",",":"))

    print(msg(f"\n入力合計: {total_rows} 行", f"\nTotal input rows: {total_rows}"))
    print(msg(f"グリッド数: {len(grid_meta)}", f"Grid count: {len(grid_meta)}"))
    print(msg(f"レコード数: {len(records)}", f"Record count: {len(records)}"))
    print(msg(f"最大spotter数/セル: {max_count}", f"Max spotter count/cell: {max_count}"))
    print(msg(f"出力: {out}", f"Output: {out}"))

if __name__ == "__main__":
    main()
