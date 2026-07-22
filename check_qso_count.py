#!/usr/bin/env python3
"""
指定条件でqso_pairs.csvから該当レコードを抽出し
QSOペアおよびロケータ別QSO数を表示するデバッグツール
"""
import csv, math, argparse, sys
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

RES_MIN = 10

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
    ap = argparse.ArgumentParser(
        description=msg("QSOペア詳細チェックツール", "QSO pair detail check tool"))
    ap.add_argument("--contest", help=msg("コンテスト識別子 (例: cqwpx_cw)",
                                          "Contest ID (e.g.: cqwpx_cw)"))
    ap.add_argument("--year",    type=int, help=msg("開催年 (例: 2024)",
                                                    "Contest year (e.g.: 2024)"))
    ap.add_argument("--center",  default="PM52",
                    help=msg("中心グリッドロケータ (デフォルト: PM52)",
                             "Center grid locator (default: PM52)"))
    ap.add_argument("--dist-km", type=float, default=250.0,
                    help=msg("中心からの距離km (デフォルト: 250)",
                             "Radius in km from center (default: 250)"))
    ap.add_argument("--hour",    type=int, help=msg("UTCアワー (0-23)", "UTC hour (0-23)"))
    ap.add_argument("--min",     type=int,
                    help=msg("UTC分 (0,10,20,30,40,50)", "UTC minute (0,10,20,30,40,50)"))
    ap.add_argument("--bands",   nargs="+", default=["40m", "20m"],
                    help=msg("バンド (例: 40m 20m 15m  デフォルト: 40m 20m)",
                             "Bands (e.g.: 40m 20m 15m  default: 40m 20m)"))
    ap.add_argument("--approx",  action="store_true",
                    help=msg("approx（cty.dat補完）データを参照",
                             "Use approx (cty.dat-supplemented) data"))
    args = ap.parse_args()

    if not args.contest:
        args.contest = input(msg("コンテスト識別子 (例: cqwpx_cw): ",
                                 "Contest ID (e.g.: cqwpx_cw): ")).strip()
    if args.year is None:
        args.year = int(input(msg("開催年 (例: 2024): ", "Contest year (e.g.: 2024): ")).strip())
    if args.hour is None:
        args.hour = int(input(msg("UTCアワー (0-23): ", "UTC hour (0-23): ")).strip())
    if args.min is None:
        args.min = int(input(msg("UTC分 (0,10,20,30,40,50): ",
                                 "UTC minute (0,10,20,30,40,50): ")).strip())

    if args.min % 10 != 0 or not (0 <= args.min <= 50):
        print(msg("エラー: UTC分は 0,10,20,30,40,50 のいずれかで指定",
                  "Error: UTC minute must be one of 0,10,20,30,40,50"))
        sys.exit(1)

    try:
        CY, CX = grid4_latlon(args.center)
    except Exception:
        print(msg(f"エラー: 無効なグリッドロケータ: {args.center}",
                  f"Error: invalid grid locator: {args.center}"))
        sys.exit(1)

    BANDS  = set(args.bands)
    t_step = (args.hour * 60 + args.min) // RES_MIN

    suffix   = "_approx" if args.approx else ""
    csv_name = f"{args.contest}_{args.year}_qso_pairs{suffix}.csv"
    csv_path = Path(__file__).resolve().parent/"contest_logs"/"csv"/csv_name

    if not csv_path.exists():
        print(msg(f"エラー: ファイルが見つかりません: {csv_path}",
                  f"Error: file not found: {csv_path}"))
        sys.exit(1)

    print(msg(f"コンテスト : {args.contest} {args.year}",
              f"Contest   : {args.contest} {args.year}"))
    print(msg(f"ソース     : {csv_name}{'  [approx]' if args.approx else ''}",
              f"Source    : {csv_name}{'  [approx]' if args.approx else ''}"))
    print(msg(f"中心       : {args.center} (lat={CY}, lon={CX})",
              f"Center    : {args.center} (lat={CY}, lon={CX})"))
    print(msg(f"距離       : {args.dist_km} km 以内",
              f"Radius    : within {args.dist_km} km"))
    print(msg(f"UTC時刻    : {args.hour:02d}:{args.min:02d}z  t_step={t_step}(Day1) / {t_step+144}(Day2)",
              f"UTC time  : {args.hour:02d}:{args.min:02d}z  t_step={t_step}(Day1) / {t_step+144}(Day2)"))
    print(msg(f"バンド     : {', '.join(sorted(BANDS))}",
              f"Bands     : {', '.join(sorted(BANDS))}"))
    print()

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
        print(msg(f"  {args.hour:02d}:{args.min:02d}z  Day{'1' if day==0 else '2'} (utc_day={day})",
                  f"  {args.hour:02d}:{args.min:02d}z  Day{'1' if day==0 else '2'} (utc_day={day})"))
        print(f"{'='*52}")
        if not any(results[day].values()):
            print(msg("  (該当なし)", "  (none)"))
            print()
            continue
        for band in sorted(BANDS):
            recs = results[day][band]
            print(msg(f"  [{band}]  {len(recs)} ペア", f"  [{band}]  {len(recs)} pairs"))
            for r in recs:
                print(f"    tx={r['grid_tx']}  rx={r['grid_rx']}  dist={r['dist_km']}km  power={r['power']}")
            loc_count = defaultdict(int)
            for r in recs:
                loc_count[r["grid_tx"]] += 1
            print(msg(f"  ロケータ別 ({len(loc_count)} グリッド):",
                      f"  By locator ({len(loc_count)} grids):"))
            for g, n in sorted(loc_count.items(), key=lambda x: -x[1]):
                print(msg(f"    {g}: {n}件", f"    {g}: {n}"))
        print()

if __name__ == "__main__":
    main()
