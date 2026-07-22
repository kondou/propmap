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

import re, csv, argparse, sys
from pathlib import Path

# ---- i18n -------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent))
try:
    from contest_utils import msg
except ImportError:
    import locale as _lc, os as _os
    def _dlang():
        for v in [_os.environ.get(e, '') for e in ('LANG', 'LC_ALL', 'LANGUAGE')]:
            if v: return 'ja' if v.lower().startswith('ja') else 'en'
        try:
            _lc.setlocale(_lc.LC_ALL, '')
            lc = _lc.getlocale()[0] or ''
            if lc.lower().startswith('ja'): return 'ja'
        except Exception: pass
        if sys.platform == 'win32':
            try:
                import winreg as _wr
                k = _wr.OpenKey(_wr.HKEY_CURRENT_USER, r'Control Panel\International')
                l = _wr.QueryValueEx(k, 'LocaleName')[0]; _wr.CloseKey(k)
                if l.startswith('ja'): return 'ja'
            except Exception: pass
        return 'en'
    _L = _dlang()
    def msg(ja, en=''): return ja if _L == 'ja' else (en or ja)
# -----------------------------------------------------------------------------

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
        description=msg("CabrilloログからRBN用spotted局グリッドCSVを生成",
                        "Generate spotted station grid CSV from Cabrillo logs for RBN")
    )
    ap.add_argument("--contest", default=None,
                    help=msg("コンテスト識別子 例: iaru, cqww_cw",
                             "Contest ID e.g.: iaru, cqww_cw"))
    ap.add_argument("--year", type=int, default=None,
                    help=msg("開催年 例: 2025", "Contest year e.g.: 2025"))
    ap.add_argument("--raw-dir", default=None,
                    help=msg("ログファイルのディレクトリ "
                             "(省略時: ~/heatmap/contest_logs/raw/{contest}_{year})",
                             "Log file directory "
                             "(default: ~/heatmap/contest_logs/raw/{contest}_{year})"))
    ap.add_argument("--out", default=None,
                    help=msg("出力CSVファイルパス "
                             "(省略時: ~/heatmap/contest_logs/rbn/{contest}_{year}_spotted_grids.csv)",
                             "Output CSV path "
                             "(default: ~/heatmap/contest_logs/rbn/{contest}_{year}_spotted_grids.csv)"))
    ap.add_argument("--pattern", default="*.txt",
                    help=msg("ログファイルのglobパターン (デフォルト: *.txt)",
                             "Glob pattern for log files (default: *.txt)"))
    args = ap.parse_args()

    if not args.contest and not (args.raw_dir and args.out):
        ap.error(msg("--contest [--year] か、--raw-dir と --out の両方を指定してください",
                     "Specify --contest [--year], or both --raw-dir and --out"))

    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from contest_utils import validate_contest, raw_log_dir, spotted_grids_csv
        if args.contest:
            validate_contest(args.contest)
        _raw = raw_log_dir(args.contest, args.year) if args.contest and args.year else None
        _out = spotted_grids_csv(args.contest, args.year) if args.contest and args.year else None
    except (ImportError, ValueError) as e:
        cid  = f"{args.contest}_{args.year}" if args.year else args.contest
        _script_dir = Path(__file__).resolve().parent
        _raw = _script_dir/"raw"/cid if cid else None
        _out = _script_dir/"rbn"/f"{cid}_spotted_grids.csv" if cid else None

    raw_dir  = Path(args.raw_dir) if args.raw_dir else _raw
    out_path = Path(args.out)     if args.out     else _out

    if not raw_dir or not out_path:
        ap.error(msg("--raw-dir と --out を指定するか、--contest と --year を指定してください",
                     "Specify --raw-dir and --out, or --contest and --year"))
        return

    if not raw_dir.exists():
        print(msg(f"エラー: ディレクトリが見つかりません: {raw_dir}",
                  f"Error: directory not found: {raw_dir}"))
        return

    log_files = sorted(raw_dir.glob(args.pattern))
    if not log_files:
        print(msg(f"エラー: ログファイルが見つかりません: {raw_dir}/{args.pattern}",
                  f"Error: no log files found: {raw_dir}/{args.pattern}"))
        return

    print(msg(f"ログディレクトリ: {raw_dir}", f"Log directory:  {raw_dir}"))
    print(msg(f"対象ファイル数:   {len(log_files)}", f"Files found:    {len(log_files)}"))

    grids = {}
    powers = {}
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

    print(msg(f"グリッドあり局:   {len(grids)}", f"With grid:      {len(grids)}"))
    print(msg(f"コールなし:       {no_call}",    f"No callsign:    {no_call}"))
    print(msg(f"グリッドなし:     {no_grid}",    f"No grid:        {no_grid}"))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["callsign", "grid", "power"])
        for call, grid in sorted(grids.items()):
            w.writerow([call, grid, powers.get(call, "UNKNOWN")])

    print(msg(f"出力: {out_path}", f"Output: {out_path}"))

if __name__ == "__main__":
    main()
