#!/usr/bin/env python3
"""
Step 4 RBN approx: spotted_grids_approx.csv を使ったRBN処理

通常版 (step4_rbn.py) との違い:
  - spotted_grids_approx.csv（cty.dat補完あり）を使用
  - spotted局のグリッドが cty.dat 由来の場合のみ出力（通常版との重複除外）

使い方:
  python3 step4_rbn_approx.py --contest iaru --year 2019
  python3 step4_rbn_approx.py --contest cqww_cw --year 2024

入力:
  RBN raw zip: ~/heatmap/contest_logs/rbn/raw/YYYYMMDD.zip
  approxグリッドDB: ~/heatmap/contest_logs/rbn/{contest}_{year}_spotted_grids_approx.csv
  ノードリスト: ~/heatmap/contest_logs/rbn/rbn_nodes.csv
出力:
  ~/heatmap/contest_logs/csv/{contest}_{year}_rbn_pairs_approx.csv
"""

import re, csv, gzip, zipfile, argparse, sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict, Counter

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

GRID_RE = re.compile(r"^[A-R]{2}[0-9]{2}([A-X]{2})?$", re.IGNORECASE)

BAND_MAP = {
    "160m": (1800, 2000), "80m":  (3500, 4000), "40m":  (7000, 7300),
    "20m":  (14000, 14350), "15m":  (21000, 21450), "10m":  (28000, 29700),
}

def freq_to_band(freq_khz):
    for name, (lo, hi) in BAND_MAP.items():
        if lo <= freq_khz <= hi:
            return name
    return None

def grid4_center(g):
    g = g.upper()
    lon = (ord(g[0]) - 65) * 20 - 180 + int(g[2]) * 2 + 1
    lat = (ord(g[1]) - 65) * 10 - 90  + int(g[3]) + 0.5
    return round(lat, 1), round(lon, 1)

def load_nodes(path):
    nodes = {}
    if not Path(path).exists():
        print(msg(f"  警告: ノードリストが見つかりません: {path}  (空dictで続行)",
                  f"  Warning: node list not found: {path}  (continuing with empty dict)"),
              file=sys.stderr)
        return nodes
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return nodes
        fn_lower = {k.lower().strip(): k for k in reader.fieldnames}
        call_col = next((fn_lower[k] for k in fn_lower
                         if k in ("callsign","call","node","spotter")), None)
        grid_col = next((fn_lower[k] for k in fn_lower
                         if k in ("grid","gridsquare","grid_square",
                                  "locator","maidenhead","grid4")), None)
        if not call_col or not grid_col:
            print(msg(f"  警告: ノードリストのcallsign/grid列が特定できません: {reader.fieldnames}",
                      f"  Warning: callsign/grid columns not found in node list: {reader.fieldnames}"))
            return nodes
        for row in reader:
            call = row[call_col].strip().upper()
            g    = row[grid_col].strip().upper()
            if not call or not g:
                continue
            base_call = call.split("-")[0]
            g4 = g[:4]
            if GRID_RE.match(g4):
                nodes[base_call] = g4
                nodes[call] = g4
    print(msg(f"  ノードリスト: {len(nodes)} エントリ",
              f"  Node list: {len(nodes)} entries"))
    return nodes

def load_spotted_grids_approx(path):
    spotted_grids  = {}
    spotted_powers = {}
    cty_calls      = set()
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            call   = row["callsign"].strip().upper()
            g      = row["grid"].strip().upper()[:4]
            source = row.get("grid_source", "log")
            if call and GRID_RE.match(g):
                spotted_grids[call] = g
                pw = row.get("power", "UNKNOWN").strip().upper()
                spotted_powers[call] = pw if pw in ("HIGH","LOW","QRP") else "UNKNOWN"
                if source != "log":
                    cty_calls.add(call)
    print(msg(f"  approxグリッドDB: {len(spotted_grids)} 局（うちcty.dat: {len(cty_calls)} 局）",
              f"  approx grid DB: {len(spotted_grids)} stations (cty.dat: {len(cty_calls)})"))
    return spotted_grids, spotted_powers, cty_calls

def open_rbn_file(path):
    import io
    p = Path(path)
    if p.suffix == ".gz":
        return gzip.open(p, "rt", encoding="utf-8", errors="replace")
    elif p.suffix == ".zip":
        zf = zipfile.ZipFile(p)
        names = zf.namelist()
        csv_names = [n for n in names if n.lower().endswith(".csv")]
        if not csv_names:
            raise ValueError(msg(f"ZIP内にCSVが見つかりません: {p}",
                                 f"No CSV found in ZIP: {p}"))
        return io.TextIOWrapper(zf.open(csv_names[0]),
                                encoding="utf-8", errors="replace", newline="")
    else:
        return open(p, newline="", encoding="utf-8", errors="replace")

def parse_rbn_date(s):
    if not s:
        return None
    s = s.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None

def main():
    ap = argparse.ArgumentParser(
        description=msg("RBN approx: cty.dat補完グリッドを使ったRBN処理",
                        "RBN approx: RBN processing using cty.dat-supplemented grids")
    )
    ap.add_argument("--contest", required=True)
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--ssn", type=int, default=None)
    ap.add_argument("--rbn-csv", nargs="+", default=None)
    ap.add_argument("--log-grids", nargs="+", default=None,
                    help=msg("spotted_grids_approx.csv のパス（複数可）",
                             "Path(s) to spotted_grids_approx.csv"))
    ap.add_argument("--nodes", default=None)
    ap.add_argument("--start", default=None)
    ap.add_argument("--end", default=None)
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--time-resolution", type=int, default=10)
    ap.add_argument("--min-snr", type=int, default=3)
    ap.add_argument("--min-wpm", type=int, default=10)
    ap.add_argument("--max-wpm", type=int, default=60)
    args = ap.parse_args()

    _resolve_ssn = None
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from contest_utils import (validate_contest, get_contest_dates, rbn_raw_zips,
                                   spotted_grids_approx_csv, rbn_pairs_approx_csv,
                                   CONTEST_CFG, resolve_ssn as _resolve_ssn)
        validate_contest(args.contest)
        cfg = CONTEST_CFG[args.contest]
        if not cfg["has_rbn"]:
            print(msg(f"情報: {args.contest} はRBNデータなし（SSBコンテスト）。スキップします。",
                      f"Info: {args.contest} has no RBN data (SSB contest). Skipping."))
            return
        _start, _end   = get_contest_dates(args.contest, args.year)
        _rbn_csvs      = rbn_raw_zips(args.contest, args.year)
        _log_grids     = [spotted_grids_approx_csv(args.contest, args.year)]
        _out_csv       = rbn_pairs_approx_csv(args.contest, args.year)
    except (ImportError, ValueError) as e:
        print(msg(f"警告: contest_utils未使用 ({e})",
                  f"Warning: contest_utils not used ({e})"))
        _start = _end = None
        _rbn_csvs  = []
        cid = f"{args.contest}_{args.year}"
        _log_grids = [Path.home()/"heatmap"/"contest_logs"/"rbn"/f"{cid}_spotted_grids_approx.csv"]
        _out_csv   = Path.home()/"heatmap"/"contest_logs"/"csv"/f"{cid}_rbn_pairs_approx.csv"

    start_dt = datetime.strptime(args.start, "%Y-%m-%d %H:%M") if args.start else _start
    end_dt   = datetime.strptime(args.end,   "%Y-%m-%d %H:%M") if args.end   else _end
    if not start_dt or not end_dt:
        print(msg("エラー: --start と --end を指定するか、contest_utils.py を同ディレクトリに置いてください",
                  "Error: specify --start and --end, or place contest_utils.py in the same directory"))
        return

    rbn_csv_paths  = ([Path(p) for p in args.rbn_csv]   if args.rbn_csv   else _rbn_csvs)
    log_grid_paths = ([Path(p) for p in args.log_grids] if args.log_grids else _log_grids)
    nodes_path     = (Path(args.nodes) if args.nodes
                      else Path(__file__).parent / "rbn" / "rbn_nodes.csv")

    out_dir = Path(args.out_dir) if args.out_dir else _out_csv.parent
    out_csv = out_dir / _out_csv.name
    out_dir.mkdir(parents=True, exist_ok=True)

    if _resolve_ssn:
        ssn = _resolve_ssn(args.contest, args.year,
                           ssn_override=args.ssn,
                           script_dir=Path(__file__).parent)
    else:
        ssn = args.ssn if args.ssn is not None else 0

    missing_grids = [p for p in log_grid_paths if not p.exists()]
    if missing_grids:
        print(msg("エラー: 以下のapproxグリッドDBが見つかりません:",
                  "Error: approx grid DB not found:"))
        for p in missing_grids: print(f"  {p}")
        print(msg("  make_spotted_grids_approx.py を先に実行してください。",
                  "  Run make_spotted_grids_approx.py first."))
        return

    rbn_csv_paths = [p for p in rbn_csv_paths if p.exists()]
    if not rbn_csv_paths:
        print(msg("エラー: RBN rawファイルが1件もありません → 空CSVを生成",
                  "Error: no RBN raw files found → generating empty CSV"))
        _fn = ["grid_tx","grid_rx","band","mode","utc_hour","utc_min",
               "utc_month","utc_day","distance_km","ssn","tier","source","lon_tx",
               "power_tx","power_rx","call_dist","band_fix","spotter_count"]
        with open(out_csv,"w",newline="",encoding="utf-8") as _f:
            csv.DictWriter(_f,fieldnames=_fn).writeheader()
        return

    print(msg(f"期間: {start_dt} 〜 {end_dt} UTC",
              f"Period: {start_dt} to {end_dt} UTC"))

    print(msg(f"\nノードリスト読み込み: {nodes_path}",
              f"\nLoading node list: {nodes_path}"))
    spotter_grids = load_nodes(nodes_path)

    cty = None
    try:
        from lookup_cty import CtyLookup
        cty = CtyLookup(verbose=False)
        print(msg("  cty.dat読み込み完了（spotter fallback用）",
                  "  cty.dat loaded (spotter fallback)"))
    except Exception as e:
        print(msg(f"  警告: cty.dat読み込み失敗 - spotter fallbackなし ({e})",
                  f"  Warning: cty.dat load failed - no spotter fallback ({e})"))

    print(msg("\napproxグリッドDB読み込み:", "\nLoading approx grid DB:"))
    spotted_grids = {}
    spotted_powers = {}
    cty_calls = set()
    for path in log_grid_paths:
        sg, sp, cc = load_spotted_grids_approx(path)
        spotted_grids.update(sg)
        spotted_powers.update(sp)
        cty_calls.update(cc)

    if not cty_calls:
        print(msg("  情報: cty.dat由来グリッドの局がありません。出力は空になります。",
                  "  Info: no stations with cty.dat-derived grids. Output will be empty."))

    res_min = args.time_resolution
    steps_per_day = 24 * 60 // res_min

    agg = defaultdict(set)
    total_rows = 0
    skipped = {"period": 0, "mode": 0, "snr": 0, "wpm": 0,
               "no_spotter_grid": 0, "no_spotted_grid": 0, "not_cty": 0, "band": 0}
    spotter_cty_ok  = 0
    unknown_spotters = Counter()
    unknown_spotted  = Counter()

    for rbn_path in rbn_csv_paths:
        print(msg(f"\nRBN CSV読み込み: {rbn_path}",
                  f"\nLoading RBN CSV: {rbn_path}"))
        try:
            fh = open_rbn_file(rbn_path)
        except Exception as e:
            print(msg(f"  エラー: {e}", f"  Error: {e}"))
            continue

        with fh:
            reader = csv.DictReader(fh)
            if not reader.fieldnames:
                print(msg("  エラー: ヘッダーなし", "  Error: no header"))
                continue
            fn_lower = {k.lower().strip(): k for k in reader.fieldnames}

            if not any(k in fn_lower for k in ("callsign","dx","date","freq","band","de","spotter")):
                _LEGACY = ["callsign","de_pfx","de_cont","freq","band",
                           "dx","dx_pfx","dx_cont","mode","db","date"]
                def _prepend(first, rest):
                    yield ','.join(str(v) for v in first)
                    yield from rest
                reader = csv.DictReader(_prepend(reader.fieldnames, fh), fieldnames=_LEGACY)
                fn_lower = {k: k for k in _LEGACY}

            def col(names):
                for n in names:
                    if n in fn_lower:
                        return fn_lower[n]
                return None

            c_spotter = col(["callsign","spotter","de"])
            c_dx      = col(["dx","spotted","call"])
            c_freq    = col(["freq","frequency"])
            c_band    = col(["band"])
            c_mode    = col(["mode","tx_mode"])
            c_db      = col(["db","snr"])
            c_speed   = col(["speed","wpm"])
            c_date    = col(["date","datetime","utc"])
            c_txmode  = col(["tx_mode","txmode"])

            if not all([c_spotter, c_dx, c_date]):
                print(msg("  エラー: 必須カラムが見つかりません",
                          "  Error: required columns not found"))
                continue

            row_count = 0
            for row in reader:
                total_rows += 1
                row_count  += 1

                dt = parse_rbn_date(row.get(c_date, ""))
                if not dt or not (start_dt <= dt <= end_dt):
                    skipped["period"] += 1
                    continue

                if c_txmode:
                    tx_mode = row.get(c_txmode, "").strip().upper()
                    if tx_mode and tx_mode != "CW":
                        skipped["mode"] += 1
                        continue
                mode_val = row.get(c_mode, "").strip().upper() if c_mode else ""
                if mode_val not in ("CQ", "CW", ""):
                    skipped["mode"] += 1
                    continue

                try:
                    db = int(float(row.get(c_db, 0)))
                except (ValueError, TypeError):
                    db = 0
                if db < args.min_snr:
                    skipped["snr"] += 1
                    continue

                try:
                    wpm = int(float(row.get(c_speed, 0)))
                except (ValueError, TypeError):
                    wpm = 0
                if wpm and not (args.min_wpm <= wpm <= args.max_wpm):
                    skipped["wpm"] += 1
                    continue

                band = None
                if c_band:
                    b_raw = row.get(c_band, "").strip().lower()
                    if b_raw in BAND_MAP:
                        band = b_raw
                if not band and c_freq:
                    try:
                        band = freq_to_band(float(row.get(c_freq, 0)))
                    except (ValueError, TypeError):
                        pass
                if not band:
                    skipped["band"] += 1
                    continue

                spotter_raw   = row.get(c_spotter, "").strip().upper()
                spotter_clean = re.sub(r'[#@].*$', '', spotter_raw)
                spotter_base  = spotter_clean.split('-')[0]
                sg = spotter_grids.get(spotter_raw) or spotter_grids.get(spotter_base)
                if not sg and cty and spotter_base:
                    grid_cty, _ = cty.lookup(spotter_base)
                    if grid_cty:
                        sg = grid_cty
                        spotter_cty_ok += 1
                if not sg:
                    skipped["no_spotter_grid"] += 1
                    if spotter_base:
                        unknown_spotters[spotter_base] += 1
                    continue

                dx_raw  = row.get(c_dx, "").strip().upper()
                dx_base = re.sub(r"[/\-].*$", "", dx_raw)
                dg = spotted_grids.get(dx_raw) or spotted_grids.get(dx_base)
                if not dg:
                    skipped["no_spotted_grid"] += 1
                    unknown_spotted[dx_base or dx_raw] += 1
                    continue

                dx_key = dx_raw if dx_raw in cty_calls else dx_base
                if dx_key not in cty_calls:
                    skipped["not_cty"] += 1
                    continue

                utc_day = (dt.date() - start_dt.date()).days
                t_step  = (utc_day * 1440 + dt.hour * 60 + dt.minute) // res_min

                pw_spotted = (spotted_powers.get(dx_raw)
                              or spotted_powers.get(dx_base) or "UNKNOWN")

                agg[(sg, dg, band, t_step, pw_spotted)].add(spotter_raw)

            print(msg(f"  読み込み行数: {row_count}", f"  Rows loaded: {row_count}"))

    print(msg("\n=== フィルタ統計 ===", "\n=== Filter statistics ==="))
    print(msg(f"  総行数:                    {total_rows:8d}",
              f"  Total rows:                {total_rows:8d}"))
    print(msg(f"  期間外:                    {skipped['period']:8d}",
              f"  Out of period:             {skipped['period']:8d}"))
    print(msg(f"  モード除外:                {skipped['mode']:8d}",
              f"  Mode filtered:             {skipped['mode']:8d}"))
    print(msg(f"  SNR不足:                   {skipped['snr']:8d}",
              f"  SNR too low:               {skipped['snr']:8d}"))
    print(msg(f"  WPM範囲外:                 {skipped['wpm']:8d}",
              f"  WPM out of range:          {skipped['wpm']:8d}"))
    print(msg(f"  バンド不明:                {skipped['band']:8d}",
              f"  Unknown band:              {skipped['band']:8d}"))
    print(msg(f"  spotter grids不明:         {skipped['no_spotter_grid']:8d}",
              f"  Unknown spotter grids:     {skipped['no_spotter_grid']:8d}"))
    print(msg(f"  spotter cty.dat解決:       {spotter_cty_ok:8d}",
              f"  Spotter resolved via cty:  {spotter_cty_ok:8d}"))
    if unknown_spotters:
        print(msg("  --- spotter 未解決 上位20 ---",
                  "  --- Top 20 unresolved spotters ---"))
        for call, cnt in unknown_spotters.most_common(20):
            print(f"    {call:<16s} {cnt:8d}")
    print(msg(f"  spotted grids不明:         {skipped['no_spotted_grid']:8d}",
              f"  Unknown spotted grids:     {skipped['no_spotted_grid']:8d}"))
    if unknown_spotted:
        print(msg("  --- spotted 未解決 上位20 ---",
                  "  --- Top 20 unresolved spotted ---"))
        for call, cnt in unknown_spotted.most_common(20):
            print(f"    {call:<16s} {cnt:8d}")
    print(msg(f"  cty.dat由来でない:         {skipped['not_cty']:8d}",
              f"  Not cty.dat-derived:       {skipped['not_cty']:8d}"))

    pairs = []
    for (sg, dg, band, t_step, pw_spotted), spotters in agg.items():
        try:
            lat_tx, lon_tx = grid4_center(sg)
            lat_rx, lon_rx = grid4_center(dg)
        except Exception:
            continue
        day_min = t_step * res_min
        utc_day = day_min // 1440
        utc_min = day_min % 1440
        pairs.append({
            "grid_tx":       sg,
            "grid_rx":       dg,
            "band":          band,
            "mode":          "CW",
            "utc_hour":      utc_min // 60,
            "utc_min":       utc_min % 60,
            "utc_month":     start_dt.month,
            "utc_day":       utc_day,
            "distance_km":   round(__import__('math').asin(
                min(1, (__import__('math').sin((lat_rx-lat_tx)*__import__('math').pi/180/2)**2 +
                        __import__('math').cos(lat_tx*__import__('math').pi/180)*
                        __import__('math').cos(lat_rx*__import__('math').pi/180)*
                        __import__('math').sin((lon_rx-lon_tx)*__import__('math').pi/180/2)**2)
                        **0.5)) * 2 * 6371, 1),
            "ssn":           ssn,
            "tier":          2,
            "source":        args.contest,
            "lon_tx":        round(lon_tx, 2),
            "power_tx":      pw_spotted,
            "power_rx":      pw_spotted,
            "call_dist":     0,
            "band_fix":      "",
            "spotter_count": len(spotters),
        })

    print(msg(f"\n集約ペア数: {len(pairs)}", f"\nAggregated pairs: {len(pairs)}"))

    fieldnames = [
        "grid_tx", "grid_rx", "band", "mode", "utc_hour", "utc_min",
        "utc_month", "utc_day", "distance_km", "ssn", "tier", "source", "lon_tx",
        "power_tx", "power_rx", "call_dist", "band_fix", "spotter_count",
    ]
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(pairs)
    print(msg(f"\nCSV出力: {out_csv}", f"\nCSV written: {out_csv}"))

if __name__ == "__main__":
    main()
