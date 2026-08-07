#!/usr/bin/env python3
"""
make_spotted_grids_approx.py:
  Cabrilloログからspotted局グリッドDBを生成（cty.datフォールバック付き）

通常版 (make_spotted_grids.py) との違い:
  - グリッドなし局について cty.dat から近似ロケータを付与
  - 出力CSVに grid_source 列追加（'log' / 'cty-xxx'）

使い方:
  python3 make_spotted_grids_approx.py --contest iaru --year 2019
  python3 make_spotted_grids_approx.py --contest cqww_cw --year 2024

入力:  ~/heatmap/contest_logs/raw/{contest}_{year}/*.txt
出力:  ~/heatmap/contest_logs/rbn/{contest}_{year}_spotted_grids_approx.csv
"""

import re, csv, sys, argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# ---- i18n -------------------------------------------------------------------
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

from lookup_cty import CtyLookup

GRID_RE     = re.compile(r'^[A-R]{2}[0-9]{2}([A-X]{2})?$', re.IGNORECASE)
GRID_FIELDS = ['GRID-LOCATOR','HQ-GRID-LOCATOR','MY-GRIDSQUARE','LOCATION-GRID','GRID']

def parse_header(text):
    result = {}
    for line in text.splitlines():
        if line.upper().startswith('QSO:'):
            break
        m = re.match(r'^([A-Z0-9\-]+):\s*(.*)', line.strip(), re.IGNORECASE)
        if m:
            result[m.group(1).upper()] = m.group(2).strip()
    return result

def get_log_grid(header):
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
        description=msg('Cabrilloログからspotted局グリッドDB生成（cty.datフォールバック付き）',
                        'Generate spotted-station grid DB from Cabrillo logs (cty.dat fallback)'))
    ap.add_argument('--contest', default=None,
                    help=msg('コンテスト識別子 (例: iaru)', 'Contest ID (e.g.: iaru)'))
    ap.add_argument('--year', type=int, default=None,
                    help=msg('開催年 (例: 2019)', 'Contest year (e.g.: 2019)'))
    ap.add_argument('--raw-dir', default=None,
                    help=msg('ログディレクトリ（--contest/--year の代替）',
                             'Log directory (alternative to --contest/--year)'))
    ap.add_argument('--out', default=None,
                    help=msg('出力CSVパス（--contest/--year の代替）',
                             'Output CSV path (alternative to --contest/--year)'))
    args = ap.parse_args()

    try:
        from contest_utils import (validate_contest, raw_log_dir,
                                   spotted_grids_approx_csv)
        if args.contest:
            validate_contest(args.contest)
        _raw = raw_log_dir(args.contest, args.year) if args.contest and args.year else None
        _out = spotted_grids_approx_csv(args.contest, args.year) \
               if args.contest and args.year else None
    except (ImportError, AttributeError, ValueError) as e:
        cid  = f'{args.contest}_{args.year}' if args.year else args.contest
        _script_dir = Path(__file__).resolve().parent
        _raw = _script_dir/'raw'/cid if cid else None
        _out = _script_dir/'rbn'/f'{cid}_spotted_grids_approx.csv' \
               if cid else None

    raw_dir  = Path(args.raw_dir) if args.raw_dir else _raw
    out_path = Path(args.out)     if args.out     else _out

    if not raw_dir or not out_path:
        ap.error(msg('--raw-dir と --out か、--contest と --year を指定してください',
                     'Specify --raw-dir and --out, or --contest and --year'))

    log_files = sorted(raw_dir.glob('*.txt'))
    if not log_files:
        print(msg(f'エラー: ログなし: {raw_dir}',
                  f'Error: no logs found: {raw_dir}'))
        return

    print(msg(f'ログ数: {len(log_files)}', f'Logs: {len(log_files)}'), file=sys.stderr)

    # ---- cty.dat ロード ----
    cty = CtyLookup()

    grids   = {}   # call → grid4
    powers  = {}
    sources = {}   # call → 'log' or 'cty-xxx'
    no_call = no_log_grid = cty_found = cty_notfound = 0

    for path in log_files:
        text   = path.read_text(encoding='utf-8', errors='replace')
        header = parse_header(text)
        call   = header.get('CALLSIGN', '').upper().strip()
        if not call:
            no_call += 1
            continue
        power = header.get('CATEGORY-POWER', 'UNKNOWN').upper().strip()
        if power not in ('HIGH', 'LOW', 'QRP'):
            power = 'UNKNOWN'
        powers[call] = power

        grid = get_log_grid(header)
        if grid:
            grids[call]   = grid
            sources[call] = 'log'
        else:
            no_log_grid += 1
            g, src = cty.lookup(call)
            if g:
                grids[call]   = g
                sources[call] = f'cty-{src}'
                cty_found += 1
            else:
                cty_notfound += 1

    print(msg(f'  ロググリッドあり : {sum(1 for s in sources.values() if s=="log")}',
              f'  Log grid found   : {sum(1 for s in sources.values() if s=="log")}'))
    print(msg(f'  cty.dat補完      : {cty_found}',
              f'  cty.dat fallback : {cty_found}'))
    print(msg(f'  グリッド不明     : {cty_notfound}',
              f'  Grid unknown     : {cty_notfound}'))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['callsign', 'grid', 'power', 'grid_source'])
        for call in sorted(grids):
            w.writerow([call, grids[call], powers.get(call,'UNKNOWN'), sources.get(call,'?')])

    print(msg(f'出力: {out_path}  ({len(grids)} 局)',
              f'Output: {out_path}  ({len(grids)} stations)'))


if __name__ == '__main__':
    main()
