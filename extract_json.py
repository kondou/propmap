#!/usr/bin/env python3
"""
指定条件でJSONレコードを切り出すスクリプト
"""
import json, argparse, sys, re
from pathlib import Path

# ---- i18n -------------------------------------------------------------------
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

BAND_NAME_TO_CODE = {
    "160m": 1, "80m": 2, "40m": 3, "20m": 4, "15m": 5, "10m": 6,
}
RES_MIN = 10

def parse_time(s):
    """
    [Nd]HH:MM 形式を t_step に変換。
    例: "0:00"→0, "12:00"→72, "1d0:00"→144, "1d12:00"→216
    """
    m = re.fullmatch(r'(?:(\d+)d)?(\d{1,2}):(\d{2})', s.strip())
    if not m:
        raise argparse.ArgumentTypeError(
            msg(f"時間形式が不正: '{s}'  正しい形式: [Nd]HH:MM  例: 12:00 / 1d6:00",
                f"Invalid time format: '{s}'  Expected: [Nd]HH:MM  e.g.: 12:00 / 1d6:00"))
    day  = int(m.group(1) or 0)
    hour = int(m.group(2))
    min_ = int(m.group(3))
    if not (0 <= hour <= 23):
        raise argparse.ArgumentTypeError(
            msg(f"時(hour)は0〜23で指定: '{s}'",
                f"Hour must be 0-23: '{s}'"))
    if not (0 <= min_ <= 59):
        raise argparse.ArgumentTypeError(
            msg(f"分(min)は0〜59で指定: '{s}'",
                f"Minute must be 0-59: '{s}'"))
    return (day * 1440 + hour * 60 + min_) // RES_MIN

def main():
    ap = argparse.ArgumentParser(
        description=msg("JSONレコードを条件で切り出す",
                        "Extract JSON records by filter conditions"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=msg("時間形式: [Nd]HH:MM  例: 12:00 / 1d6:00 (Day2 06:00)",
                   "Time format: [Nd]HH:MM  e.g.: 12:00 / 1d6:00 (Day2 06:00)"))
    ap.add_argument("input", help=msg("入力JSONファイル", "Input JSON file"))
    ap.add_argument("--grid",
                    help=msg("グリッド(部分一致) 例: PM95",
                             "Grid filter (partial match) e.g.: PM95"))
    ap.add_argument("--band",
                    help=msg(f"バンド名 {list(BAND_NAME_TO_CODE.keys())}",
                             f"Band name {list(BAND_NAME_TO_CODE.keys())}"))
    ap.add_argument("--from", dest="t_from", type=parse_time, default=0,
                    metavar="[Nd]HH:MM",
                    help=msg("開始時刻 (デフォルト: 0:00)", "Start time (default: 0:00)"))
    ap.add_argument("--to",   dest="t_to",   type=parse_time, default=9999,
                    metavar="[Nd]HH:MM",
                    help=msg("終了時刻 (デフォルト: 制限なし)", "End time (default: no limit)"))
    ap.add_argument("--out",
                    help=msg("出力JSONファイル（省略時は標準出力）",
                             "Output JSON file (default: stdout)"))
    args = ap.parse_args()

    if args.band is not None:
        band_key = args.band.lower()
        if band_key not in BAND_NAME_TO_CODE:
            ap.error(msg(f"不明なバンド: '{args.band}'  指定可能: {list(BAND_NAME_TO_CODE.keys())}",
                         f"Unknown band: '{args.band}'  Valid: {list(BAND_NAME_TO_CODE.keys())}"))
        band_code = BAND_NAME_TO_CODE[band_key]
    else:
        band_code = None

    if args.t_from > args.t_to:
        ap.error(msg(f"--from が --to より後になっています ({args.t_from} > {args.t_to})",
                     f"--from is later than --to ({args.t_from} > {args.t_to})"))

    print(msg(f"読み込み中: {args.input}", f"Loading: {args.input}"), file=sys.stderr)
    data = json.loads(Path(args.input).read_text())

    filtered = []
    for r in data["records"]:
        rx4, b_code, mode_code, t_step, tx4, count, power_code = r
        if band_code is not None and b_code != band_code:
            continue
        if not (args.t_from <= t_step <= args.t_to):
            continue
        if args.grid:
            if args.grid.upper() not in rx4.upper() and args.grid.upper() not in tx4.upper():
                continue
        filtered.append(r)

    used_grids = set()
    for r in filtered:
        used_grids.add(r[0]); used_grids.add(r[4])

    out = {
        "meta":    data["meta"],
        "grids":   {k: v for k, v in data["grids"].items() if k in used_grids},
        "records": filtered,
    }

    result = json.dumps(out, ensure_ascii=False, separators=(',', ':'))
    if args.out:
        Path(args.out).write_text(result)
        print(msg(f"出力: {args.out} ({len(filtered)}件)",
                  f"Output: {args.out} ({len(filtered)} records)"), file=sys.stderr)
    else:
        print(result)

if __name__ == "__main__":
    main()
