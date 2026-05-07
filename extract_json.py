#!/usr/bin/env python3
"""
指定条件でJSONレコードを切り出すスクリプト
"""
import json, argparse, sys, re
from pathlib import Path

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
            f"時間形式が不正: '{s}'  正しい形式: [Nd]HH:MM  例: 12:00 / 1d6:00")
    day  = int(m.group(1) or 0)
    hour = int(m.group(2))
    min_ = int(m.group(3))
    if not (0 <= hour <= 23):
        raise argparse.ArgumentTypeError(f"時(hour)は0〜23で指定: '{s}'")
    if not (0 <= min_ <= 59):
        raise argparse.ArgumentTypeError(f"分(min)は0〜59で指定: '{s}'")
    return (day * 1440 + hour * 60 + min_) // RES_MIN

def main():
    ap = argparse.ArgumentParser(
        description="JSONレコードを条件で切り出す",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="時間形式: [Nd]HH:MM  例: 12:00 / 1d6:00 (Day2 06:00)")
    ap.add_argument("input", help="入力JSONファイル")
    ap.add_argument("--grid", help="グリッド(部分一致) 例: PM95")
    ap.add_argument("--band", help=f"バンド名 {list(BAND_NAME_TO_CODE.keys())}")
    ap.add_argument("--from", dest="t_from", type=parse_time, default=0,
                    metavar="[Nd]HH:MM", help="開始時刻 (デフォルト: 0:00)")
    ap.add_argument("--to",   dest="t_to",   type=parse_time, default=9999,
                    metavar="[Nd]HH:MM", help="終了時刻 (デフォルト: 制限なし)")
    ap.add_argument("--out", help="出力JSONファイル（省略時は標準出力）")
    args = ap.parse_args()

    if args.band is not None:
        band_key = args.band.lower()
        if band_key not in BAND_NAME_TO_CODE:
            ap.error(f"不明なバンド: '{args.band}'  指定可能: {list(BAND_NAME_TO_CODE.keys())}")
        band_code = BAND_NAME_TO_CODE[band_key]
    else:
        band_code = None

    if args.t_from > args.t_to:
        ap.error(f"--from が --to より後になっています ({args.t_from} > {args.t_to})")

    print(f"読み込み中: {args.input}", file=sys.stderr)
    data = json.loads(Path(args.input).read_text())

    filtered = []
    for r in data["records"]:
        # r: [rx4, band_code, mode_code, t_step, tx4, count, power_code]
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
        print(f"出力: {args.out} ({len(filtered)}件)", file=sys.stderr)
    else:
        print(result)

if __name__ == "__main__":
    main()
