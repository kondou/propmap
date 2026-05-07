#!/usr/bin/env python3
"""
Step 4 RBN: RBN raw dataからヒートマップ用CSVを生成

使い方:
  python3 step4_rbn.py \\
    --rbn-csv rbndata_20190713.csv rbndata_20190714.csv \\
    --log-grids ~/heatmap/contest_logs/csv/iaru_2019_qso_pairs.csv \\
    --nodes rbn_nodes.csv \\
    --contest iaru_2019 \\
    --start "2019-07-13 12:00" --end "2019-07-14 12:00"

入力:
  --rbn-csv     RBN raw CSV（複数指定可、zip不可・展開済みを渡す）
  --log-grids   step4出力CSV（spotted局のグリッド解決に使用）
                またはstep4で生成したログのグリッドDBファイル
  --nodes       RBNノードリストCSV（spotter→グリッド対応）
  --contest     コンテスト識別子（出力ファイル名に使用）
  --start/--end コンテスト期間（UTC, "YYYY-MM-DD HH:MM"形式）

出力:
  ~/heatmap/contest_logs/csv/{contest}_rbn_pairs.csv

RBN raw CSVフォーマット:
  callsign, de_pfx, de_cont, freq, band, dx, dx_pfx, dx_cont,
  mode, db, date, speed, tx_mode

ノードリストCSVフォーマット（reversebeacon.net/nodes/ の詳細リスト）:
  callsign, grid  （最低限この2列があれば他は不問）

誤スポットフィルタ:
  - tx_mode != CW はスキップ
  - SNR (db) が --min-snr 未満はスキップ（デフォルト: 3）
  - WPM (speed) が --min-wpm 未満または --max-wpm 超はスキップ
    （デフォルト: 10〜60）
  - 同一 spotter×spotted×band×t_step 内の重複スポットは1件に集約

カウント仕様:
  - 同一ロケータペア（spotter_grid4×spotted_grid4）×band×t_step で
    ユニークspotter数をカウント（スポット数ではない）
  - spotted局はlogsのグリッドを使用（QSOペアCSVから抽出）
  - spotted局がlogsにない場合はスキップ
  - spotter局がノードリストにグリッドがない場合はスキップ
"""

import re, csv, gzip, zipfile, argparse
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

GRID_RE = re.compile(r"^[A-R]{2}[0-9]{2}([A-X]{2})?$", re.IGNORECASE)

BAND_MAP = {
    "160m": (1800, 2000),
    "80m":  (3500, 4000),
    "40m":  (7000, 7300),
    "20m":  (14000, 14350),
    "15m":  (21000, 21450),
    "10m":  (28000, 29700),
}

def freq_to_band(freq_khz):
    for name, (lo, hi) in BAND_MAP.items():
        if lo <= freq_khz <= hi:
            return name
    return None

def grid4(g):
    """グリッドを4桁に正規化"""
    return g.upper()[:4]

def grid4_center(g):
    g = g.upper()
    lon = (ord(g[0]) - 65) * 20 - 180 + int(g[2]) * 2 + 1
    lat = (ord(g[1]) - 65) * 10 - 90  + int(g[3]) + 0.5
    return round(lat, 1), round(lon, 1)

def load_nodes(path):
    """
    RBNノードリストCSVを読み込み {callsign: grid4} を返す。
    カラム名は柔軟に対応（callsign/call/node, grid/gridsquare/locator等）
    """
    nodes = {}
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        # ヘッダー行を探す
        sample = f.read(4096)
        f.seek(0)
        # callsign列とgrid列を探す
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
            print(f"  警告: ノードリストのcallsign/grid列が特定できません")
            print(f"  検出されたカラム: {reader.fieldnames}")
            return nodes
        for row in reader:
            call = row[call_col].strip().upper()
            g    = row[grid_col].strip().upper()
            if not call or not g:
                continue
            # サフィックス（-7等）を除去
            base_call = call.split("-")[0]
            g4 = g[:4]
            if GRID_RE.match(g4):
                nodes[base_call] = g4
                nodes[call] = g4  # サフィックス付きも登録
    print(f"  ノードリスト: {len(nodes)} エントリ")
    return nodes

def load_spotted_grids(csv_paths):
    """
    make_spotted_grids.py出力CSV（callsign,grid,power形式）を読み込む。
    戻り値: (spotted_grids, spotted_powers)
      spotted_grids: {call: grid4}
      spotted_powers: {call: power_str}  HIGH/LOW/QRP/UNKNOWN
    """
    spotted_grids  = {}
    spotted_powers = {}
    for path in csv_paths:
        with open(path, newline="", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            fn = {k.lower().strip() for k in (reader.fieldnames or [])}
            fn_map = {k.lower().strip(): k for k in (reader.fieldnames or [])}
            call_col  = fn_map.get("callsign") or fn_map.get("call")
            grid_col  = fn_map.get("grid")
            power_col = fn_map.get("power")
            if not call_col or not grid_col:
                continue
            for row in reader:
                call = row[call_col].strip().upper()
                g    = row[grid_col].strip().upper()
                g4   = g[:4]
                if call and GRID_RE.match(g4):
                    spotted_grids[call] = g4
                    if power_col:
                        pw = row[power_col].strip().upper()
                        spotted_powers[call] = pw if pw in ("HIGH","LOW","QRP") else "UNKNOWN"
                    else:
                        spotted_powers[call] = "UNKNOWN"

    print(f"  spotted局グリッドDB: {len(spotted_grids)} 局")
    return spotted_grids, spotted_powers

def open_rbn_file(path):
    """
    gzip/zip/通常CSVを透過的に開いてテキストストリームを返す。

    対応フォーマット:
      .csv      通常CSVテキストファイル
      .csv.gz   gzip圧縮CSV
      .zip      ZIP圧縮CSV（ZIP内の最初の.csvファイルを使用）
                ※RBNサイトからダウンロードしたzipはそのまま渡せる
    """
    import io
    p = Path(path)
    if p.suffix == ".gz":
        return gzip.open(p, "rt", encoding="utf-8", errors="replace")
    elif p.suffix == ".zip":
        zf = zipfile.ZipFile(p)
        names = zf.namelist()
        csv_names = [n for n in names if n.lower().endswith(".csv")]
        if not csv_names:
            raise ValueError(f"ZIP内にCSVが見つかりません: {p}  (内容: {names})")
        # バイナリストリームをテキストストリームにラップ
        return io.TextIOWrapper(zf.open(csv_names[0]),
                                encoding="utf-8", errors="replace", newline="")
    else:
        return open(p, newline="", encoding="utf-8", errors="replace")

def parse_rbn_date(s):
    """RBN dateフォーマット "YYYY-MM-DD HH:MM:SS" をdatetimeに"""
    if s is None:
        return None
    s = s.strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None

def main():
    ap = argparse.ArgumentParser(
        description="RBN raw dataからヒートマップ用CSVを生成"
    )
    ap.add_argument("--contest", required=True,
                    help="コンテスト識別子 例: iaru, cqww_cw")
    ap.add_argument("--year", type=int, required=True,
                    help="開催年 例: 2025")
    ap.add_argument("--ssn", type=int, default=None,
                    help="開催月の月平均SSN（省略時: SN_m_tot_V2.0.txt から自動取得）")
    ap.add_argument("--rbn-csv", nargs="+", default=None,
                    help="RBN raw CSVファイル（省略時: ~/heatmap/contest_logs/rbn/raw/YYYYMMDD.zip）。"
                         ".csv / .csv.gz / .zip いずれも可。")
    ap.add_argument("--log-grids", nargs="+", default=None,
                    help="spotted局グリッドDBファイル "
                         "(省略時: ~/heatmap/contest_logs/rbn/{contest}_{year}_spotted_grids.csv)")
    ap.add_argument("--nodes", default=None,
                    help="RBNノードリストCSV (省略時: ~/heatmap/contest_logs/rbn/rbn_nodes.csv)")
    ap.add_argument("--start", default=None,
                    help="コンテスト開始UTC (省略時: --contestと--yearから自動計算)")
    ap.add_argument("--end", default=None,
                    help="コンテスト終了UTC (省略時: --contestと--yearから自動計算)")
    ap.add_argument("--out-dir", default=None,
                    help="出力先ディレクトリ（省略時: ~/heatmap/contest_logs/csv/）")
    ap.add_argument("--time-resolution", type=int, default=10,
                    help="時間解像度（分）（デフォルト: 10）")
    ap.add_argument("--min-snr", type=int, default=3,
                    help="最小SNR dB（デフォルト: 3）")
    ap.add_argument("--min-wpm", type=int, default=10,
                    help="最小WPM（デフォルト: 10）")
    ap.add_argument("--max-wpm", type=int, default=60,
                    help="最大WPM（デフォルト: 60）")
    args = ap.parse_args()

    # contest_utils でパス・日程解決
    _resolve_ssn = None
    try:
        import sys; sys.path.insert(0, str(Path(__file__).parent))
        from contest_utils import (validate_contest, get_contest_dates, rbn_raw_zips,
                                   spotted_grids_csv, rbn_pairs_csv, CONTEST_CFG,
                                   resolve_ssn as _resolve_ssn)
        validate_contest(args.contest)
        cfg = CONTEST_CFG[args.contest]
        if not cfg["has_rbn"]:
            print(f"情報: {args.contest} はRBNデータなし（SSBコンテスト）。スキップします。")
            return
        _start, _end = get_contest_dates(args.contest, args.year)
        _rbn_csvs    = rbn_raw_zips(args.contest, args.year)
        _log_grids   = [spotted_grids_csv(args.contest, args.year)]
        _out_csv     = rbn_pairs_csv(args.contest, args.year)
    except (ImportError, ValueError) as e:
        print(f"警告: contest_utils未使用 ({e})")
        _start = _end = None
        _rbn_csvs  = []
        cid = f"{args.contest}_{args.year}"
        _log_grids = [Path.home()/"heatmap"/"contest_logs"/"rbn"/f"{cid}_spotted_grids.csv"]
        _out_csv   = Path.home()/"heatmap"/"contest_logs"/"csv"/f"{cid}_rbn_pairs.csv"

    start_dt = (datetime.strptime(args.start, "%Y-%m-%d %H:%M")
                if args.start else _start)
    end_dt   = (datetime.strptime(args.end,   "%Y-%m-%d %H:%M")
                if args.end   else _end)
    if not start_dt or not end_dt:
        print("エラー: --start と --end を指定するか、contest_utils.py を同ディレクトリに置いてください")
        return

    rbn_csv_paths  = ([Path(p) for p in args.rbn_csv]   if args.rbn_csv   else _rbn_csvs)
    log_grid_paths = ([Path(p) for p in args.log_grids] if args.log_grids else _log_grids)
    nodes_path     = (Path(args.nodes) if args.nodes
                      else Path.home()/"heatmap"/"contest_logs"/"rbn"/"rbn_nodes.csv")

    out_dir = Path(args.out_dir) if args.out_dir else _out_csv.parent
    out_csv = out_dir / _out_csv.name
    out_dir.mkdir(parents=True, exist_ok=True)

    # SSN解決（contest_utils.resolve_ssn を優先、未使用時はSSN=0）
    if _resolve_ssn:
        ssn = _resolve_ssn(args.contest, args.year,
                           ssn_override=args.ssn,
                           script_dir=Path(__file__).parent)
    else:
        ssn = args.ssn if args.ssn is not None else 0
        if ssn == 0:
            print("警告: contest_utils未使用のためSSN=0を使用します。")

    # spotted局グリッドDBの存在確認
    missing_grids = [p for p in log_grid_paths if not p.exists()]
    if missing_grids:
        print(f"エラー: 以下のspotted局グリッドDBが見つかりません:")
        for p in missing_grids: print(f"  {p}")
        print("  make_spotted_grids.py を先に実行してください。")
        return
    log_grid_paths = [p for p in log_grid_paths if p.exists()]

    # RBN zipファイルの存在確認
    missing = [p for p in rbn_csv_paths if not p.exists()]
    if missing:
        print(f"警告: 以下のRBN rawファイルが見つかりません:")
        for p in missing: print(f"  {p}")
        rbn_csv_paths = [p for p in rbn_csv_paths if p.exists()]
        if not rbn_csv_paths:
            print("エラー: RBN rawファイルが1件もありません")
            return

    print(f"期間: {start_dt} 〜 {end_dt} UTC")

    # ノードリスト読み込み
    print(f"\nノードリスト読み込み: {nodes_path}")
    spotter_grids = load_nodes(nodes_path)

    # spotted局グリッドDB読み込み
    print(f"\nspotted局グリッドDB読み込み:")
    spotted_grids, spotted_powers = load_spotted_grids(log_grid_paths)

    if not spotted_grids:
        print("  エラー: spotted局グリッドDBが空です。")
        print("  make_spotted_grids.py を先に実行してください。")
        return

    res_min = args.time_resolution
    steps_per_day = 24 * 60 // res_min

    # RBN raw CSV処理
    agg = defaultdict(set)
    total_rows = 0
    skipped = {"period": 0, "mode": 0, "snr": 0, "wpm": 0,
               "no_spotter_grid": 0, "no_spotted_grid": 0, "band": 0}

    for rbn_path in rbn_csv_paths:
        print(f"\nRBN CSV読み込み: {rbn_path}")
        try:
            fh = open_rbn_file(rbn_path)
        except Exception as e:
            print(f"  エラー: {e}")
            continue

        with fh:
            reader = csv.DictReader(fh)
            if not reader.fieldnames:
                print("  エラー: ヘッダーなし")
                continue
            fn_lower = {k.lower().strip(): k for k in reader.fieldnames}

            # カラム名マッピング（柔軟対応）
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
                missing = [v for v,c in [("spotter",c_spotter),("dx",c_dx),("date",c_date)] if not c]
                print(f"  エラー: 必須カラムが見つかりません: {missing}")
                print(f"  検出カラム: {reader.fieldnames}")
                print(f"  ヒント: RBN CSVの期待するヘッダー:")
                print(f"    callsign,de_pfx,de_cont,freq,band,dx,dx_pfx,dx_cont,mode,db,date,speed,tx_mode")
                continue

            row_count = 0
            for row in reader:
                total_rows += 1
                row_count  += 1

                # 日時パース・期間フィルタ
                dt = parse_rbn_date(row.get(c_date, ""))
                if not dt or not (start_dt <= dt <= end_dt):
                    skipped["period"] += 1
                    continue

                # モードフィルタ（CWのみ）
                tx_mode = row.get(c_txmode or c_mode, "").strip().upper()
                if tx_mode and tx_mode != "CW":
                    skipped["mode"] += 1
                    continue
                mode_val = row.get(c_mode, "").strip().upper()
                if mode_val not in ("CQ", "CW", ""):
                    skipped["mode"] += 1
                    continue

                # SNRフィルタ
                try:
                    db = int(float(row.get(c_db, 0)))
                except (ValueError, TypeError):
                    db = 0
                if db < args.min_snr:
                    skipped["snr"] += 1
                    continue

                # WPMフィルタ
                try:
                    wpm = int(float(row.get(c_speed, 0)))
                except (ValueError, TypeError):
                    wpm = 0
                if wpm and not (args.min_wpm <= wpm <= args.max_wpm):
                    skipped["wpm"] += 1
                    continue

                # バンド判定
                band = None
                if c_band:
                    b_raw = row.get(c_band, "").strip().lower()
                    # "20m" → "20m" 等
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

                # spotter グリッド解決
                spotter_raw = row.get(c_spotter, "").strip().upper()
                spotter_base = spotter_raw.split("-")[0]
                sg = spotter_grids.get(spotter_raw) or spotter_grids.get(spotter_base)
                if not sg:
                    skipped["no_spotter_grid"] += 1
                    continue

                # spotted グリッド解決（ログから）
                dx_raw = row.get(c_dx, "").strip().upper()
                dx_base = re.sub(r"[/\-].*$", "", dx_raw)  # /P等を除去
                dg = spotted_grids.get(dx_raw) or spotted_grids.get(dx_base)
                if not dg:
                    skipped["no_spotted_grid"] += 1
                    continue

                # t_step計算（48h対応: start_dtからの経過日数を加算）
                utc_day = (dt.date() - start_dt.date()).days
                t_step = (utc_day * 1440 + dt.hour * 60 + dt.minute) // res_min

                # spotted局のパワー取得
                pw_spotted = spotted_powers.get(dx_raw) or spotted_powers.get(dx_base) or "UNKNOWN"

                # 集約: ユニークspotter数をカウント（キーにspottedパワーを追加）
                agg[(sg, dg, band, t_step, pw_spotted)].add(spotter_raw)

            print(f"  読み込み行数: {row_count}")

    # 統計表示
    print(f"\n=== フィルタ統計 ===")
    print(f"  総行数:               {total_rows:8d}")
    print(f"  期間外:               {skipped['period']:8d}")
    print(f"  モード除外:           {skipped['mode']:8d}")
    print(f"  SNR不足:              {skipped['snr']:8d}")
    print(f"  WPM範囲外:            {skipped['wpm']:8d}")
    print(f"  バンド不明:           {skipped['band']:8d}")
    print(f"  spotter grids不明:    {skipped['no_spotter_grid']:8d}")
    print(f"  spotted grids不明:    {skipped['no_spotted_grid']:8d}")

    # CSV出力
    # フォーマットはstep4互換（call_dist=0, band_fix=""を追加）
    # spotter_countカラムを追加（step5_rbnで参照）
    pairs = []
    for (sg, dg, band, t_step, pw_spotted), spotters in agg.items():
        try:
            lat_tx, lon_tx = grid4_center(sg)
            lat_rx, lon_rx = grid4_center(dg)
        except Exception:
            continue
        # t_stepから日内分数と日数を逆算
        day_min   = t_step * res_min          # コンテスト開始からの通算分
        utc_day   = day_min // 1440
        utc_min   = day_min % 1440            # 日内分数
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
            "power_tx":      pw_spotted,   # spotter(tx)ではなくspotted局のパワー
            "power_rx":      pw_spotted,   # rx側も同じspotted局のパワー
            "call_dist":     0,
            "band_fix":      "",
            "spotter_count": len(spotters),
        })

    print(f"\n集約ペア数: {len(pairs)}")
    if not pairs:
        print("出力なし")
        return

    from collections import Counter
    print(f"\n=== バンド別 ===")
    for b, c in sorted(Counter(p["band"] for p in pairs).items(),
                       key=lambda x: -x[1]):
        print(f"  {b:6s}: {c:6d}")
    print(f"\n=== spotter数分布 ===")
    dist = Counter(p["spotter_count"] for p in pairs)
    for n in sorted(dist):
        print(f"  {n:3d} spotters: {dist[n]:6d} ペア")

    fieldnames = [
        "grid_tx", "grid_rx", "band", "mode", "utc_hour", "utc_min",
        "utc_month", "utc_day", "distance_km", "ssn", "tier", "source", "lon_tx",
        "power_tx", "power_rx", "call_dist", "band_fix", "spotter_count",
    ]
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(pairs)
    print(f"\nCSV出力: {out_csv}")

if __name__ == "__main__":
    main()
