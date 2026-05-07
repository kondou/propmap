#!/usr/bin/env python3
"""
make_spotted_grids.py: Cabrilloログからspotted局グリッドDB(callsign,grid)を生成

使い方:
  python3 make_spotted_grids.py --contest iaru_2019
  python3 make_spotted_grids.py --contest cqww_cw_2024 --raw-dir ~/mydir/logs
  python3 make_spotted_grids.py --raw-dir ~/heatmap/contest_logs/raw/iaru_2019 \\
                                 --out ~/heatmap/contest_logs/rbn/iaru_2019_spotted_grids.csv

入力:  ~/heatmap/contest_logs/raw/{contest}/*.txt  (Cabrilloフォーマット)
出力:  ~/heatmap/contest_logs/rbn/{contest}_spotted_grids.csv

グリッド取得元（優先順）:
  GRID-LOCATOR, HQ-GRID-LOCATOR, MY-GRIDSQUARE, LOCATION-GRID, GRID
"""

import re, csv, argparse
from pathlib import Path

GRID_RE     = re.compile(r'^[A-R]{2}[0-9]{2}([A-X]{2})?$', re.IGNORECASE)
GRID_FIELDS = ["GRID-LOCATOR","HQ-GRID-LOCATOR","MY-GRIDSQUARE","LOCATION-GRID","GRID"]

def parse_header(text):
    result = {}
    for line in text.splitlines():
        if line.upper().startswith("QSO:"):
            break
        m = re.match(r'^([A-Z0-9\-]+):\s*(.*)', line.strip(), re.IGNORECASE)
        if m:
            result[m.group(1).upper()] = m.group(2).strip()
    return result

def get_grid(header):
    for field in GRID_FIELDS:
        if field in header:
            parts = header[field].split()
            if not parts:
                continue
            val = parts[0].upper()[:4]
            if GRID_RE.match(val):
                return val
    return None

def main():
    ap = argparse.ArgumentParser(
        description="CabrilloログからRBN用spotted局グリッドCSVを生成"
    )
    ap.add_argument("--contest", default=None,
                    help="コンテスト識別子 例: iaru, cqww_cw")
    ap.add_argument("--year", type=int, default=None,
                    help="開催年 例: 2025")
    ap.add_argument("--raw-dir", default=None,
                    help="ログファイルのディレクトリ "
                         "(省略時: ~/heatmap/contest_logs/raw/{contest}_{year})")
    ap.add_argument("--out", default=None,
                    help="出力CSVファイルパス "
                         "(省略時: ~/heatmap/contest_logs/rbn/{contest}_{year}_spotted_grids.csv)")
    ap.add_argument("--pattern", default="*.txt",
                    help="ログファイルのglobパターン (デフォルト: *.txt)")
    args = ap.parse_args()

    if not args.contest and not (args.raw_dir and args.out):
        ap.error("--contest [--year] か、--raw-dir と --out の両方を指定してください")

    # パス解決
    try:
        import sys; sys.path.insert(0, str(Path(__file__).parent))
        from contest_utils import validate_contest, raw_log_dir, spotted_grids_csv
        if args.contest:
            validate_contest(args.contest)
        _raw = raw_log_dir(args.contest, args.year) if args.contest and args.year else None
        _out = spotted_grids_csv(args.contest, args.year) if args.contest and args.year else None
    except (ImportError, ValueError) as e:
        cid  = f"{args.contest}_{args.year}" if args.year else args.contest
        _raw = Path.home()/"heatmap"/"contest_logs"/"raw"/cid if cid else None
        _out = Path.home()/"heatmap"/"contest_logs"/"rbn"/f"{cid}_spotted_grids.csv" if cid else None

    raw_dir  = Path(args.raw_dir) if args.raw_dir else _raw
    out_path = Path(args.out)     if args.out     else _out

    if not raw_dir or not out_path:
        ap.error("--raw-dir と --out を指定するか、--contest と --year を指定してください")
        return

    if not raw_dir.exists():
        print(f"エラー: ディレクトリが見つかりません: {raw_dir}")
        return

    log_files = sorted(raw_dir.glob(args.pattern))
    if not log_files:
        print(f"エラー: ログファイルが見つかりません: {raw_dir}/{args.pattern}")
        return

    print(f"ログディレクトリ: {raw_dir}")
    print(f"対象ファイル数:   {len(log_files)}")

    grids = {}   # call → grid4
    powers = {}  # call → power
    no_call = 0
    no_grid = 0

    for path in log_files:
        text = path.read_text(encoding="utf-8", errors="replace")
        header = parse_header(text)
        call = header.get("CALLSIGN", "").upper().strip()
        if not call:
            no_call += 1
            continue
        grid = get_grid(header)
        if not grid:
            no_grid += 1
            continue
        power = header.get("CATEGORY-POWER", "UNKNOWN").upper().strip()
        if power not in ("HIGH", "LOW", "QRP"):
            power = "UNKNOWN"
        grids[call] = grid
        powers[call] = power

    print(f"グリッドあり局:   {len(grids)}")
    print(f"コールなし:       {no_call}")
    print(f"グリッドなし:     {no_grid}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["callsign", "grid", "power"])
        for call, grid in sorted(grids.items()):
            w.writerow([call, grid, powers.get(call, "UNKNOWN")])

    print(f"出力: {out_path}")

if __name__ == "__main__":
    main()
