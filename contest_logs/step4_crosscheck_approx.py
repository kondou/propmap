#!/usr/bin/env python3
"""
Step 4 approx: spotted_grids_approx.csv を使ったQSOクロスチェック

通常版 (step4_crosscheck.py) との違い:
  - approxグリッドDB（make_spotted_grids_approx.py出力）からグリッドを取得
  - 少なくとも一方のグリッドが cty.dat 由来の場合のみ出力（通常版との重複除外）
    ※「少なくとも一方」は両方cty.datの場合も含む
  - 注釈ログ出力先: annotated_approx/ サブディレクトリ

オプション・デフォルト値は step4_crosscheck.py と同一。

使い方:
  python3 step4_crosscheck_approx.py --contest iaru --year 2019
  python3 step4_crosscheck_approx.py --contest cqww_cw --year 2024 \
      --max-call-dist 2 --band-fix-window 15 --annotate-logs

入力:  ~/heatmap/contest_logs/raw/{contest}_{year}/*.txt
       ~/heatmap/contest_logs/rbn/{contest}_{year}_spotted_grids_approx.csv
出力:  ~/heatmap/contest_logs/csv/{contest}_{year}_qso_pairs_approx.csv
       ~/heatmap/contest_logs/csv/annotated_approx/{contest}_{year}/*.txt  (--annotate-logs 時)
"""

import re, csv, math, argparse, sys
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict, Counter

# ---- i18n ----------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent))
try:
    from contest_utils import msg
except ImportError:
    import locale as _lc, os as _os
    def _dlang():
        for v in [_os.environ.get(e,'') for e in ('LANG','LC_ALL','LANGUAGE')]:
            if v: return 'ja' if v.lower().startswith('ja') else 'en'
        try:
            _lc.setlocale(_lc.LC_ALL,'')
            lc = _lc.getlocale()[0] or ''
            if lc.lower().startswith('ja'): return 'ja'
        except Exception: pass
        if sys.platform == 'win32':
            try:
                import winreg as _wr
                k = _wr.OpenKey(_wr.HKEY_CURRENT_USER, r'Control Panel\International')
                l = _wr.QueryValueEx(k,'LocaleName')[0]; _wr.CloseKey(k)
                if l.startswith('ja'): return 'ja'
            except Exception: pass
        return 'en'
    _L = _dlang()
    def msg(ja, en=''): return ja if _L == 'ja' else (en or ja)
# --------------------------------------------------------------------------

GRID_RE     = re.compile(r"^[A-R]{2}[0-9]{2}([A-X]{2})?$", re.IGNORECASE)
TIME_TOL    = 15

QSO_RE = re.compile(
    r"^(QSO:\s+\d+\s+\w+\s+\d{4}-\d{2}-\d{2}\s+\d{4}\s+"
    r"\S+\s+\S+\s+\S+\s+(\S+)\s+\S+\s+\S+)(.*)",
    re.IGNORECASE
)
QSO_PARSE_RE = re.compile(
    r"^QSO:\s+(\d+)\s+(\w+)\s+(\d{4}-\d{2}-\d{2})\s+(\d{4})\s+"
    r"(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)",
    re.IGNORECASE
)

_STROKE_RE = re.compile(r'^(.+)/(?:QRP|MM|AM|P|M|\d)$', re.IGNORECASE)
def normalize_call(cs):
    m = _STROKE_RE.match(cs.upper().strip())
    return m.group(1) if m else cs.upper().strip()

def levenshtein(a, b):
    if a == b: return 0
    if len(a) < len(b): a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i]
        for j, cb in enumerate(b, 1):
            curr.append(min(prev[j] + 1, curr[j-1] + 1, prev[j-1] + (ca != cb)))
        prev = curr
    return prev[-1]

def freq_to_band(freq_khz):
    for lo, hi, name in [
        (1800, 2000, "160m"), (3500, 4000, "80m"), (7000, 7300, "40m"),
        (14000, 14350, "20m"), (21000, 21450, "15m"), (28000, 29700, "10m")
    ]:
        if lo <= freq_khz <= hi:
            return name
    return None

def grid_to_latlon(grid):
    g = grid.upper()
    lon = (ord(g[0]) - 65) * 20 - 180
    lat = (ord(g[1]) - 65) * 10 - 90
    if len(g) >= 4:
        lon += int(g[2]) * 2 + 1
        lat += int(g[3]) + 0.5
    else:
        lon += 10; lat += 5
    if len(g) >= 6:
        lon += (ord(g[4]) - 65) * 5 / 60 + 2.5 / 60
        lat += (ord(g[5]) - 65) * 2.5 / 60 + 1.25 / 60
    return lat, lon

def gcd_km(lat1, lon1, lat2, lon2):
    R = 6371.0; p = math.pi / 180
    a = (math.sin((lat2 - lat1) * p / 2) ** 2 +
         math.cos(lat1 * p) * math.cos(lat2 * p) *
         math.sin((lon2 - lon1) * p / 2) ** 2)
    return round(2 * R * math.asin(math.sqrt(min(1, a))), 1)

def parse_header(text):
    result = {}
    for line in text.splitlines():
        if line.upper().startswith("QSO:"):
            break
        m = re.match(r"^([A-Z0-9\-]+):\s*(.*)", line.strip(), re.IGNORECASE)
        if m:
            result[m.group(1).upper()] = m.group(2).strip()
    return result

def parse_qsos(text):
    qsos = []
    for lineno, line in enumerate(text.splitlines()):
        m = QSO_PARSE_RE.match(line.strip())
        if not m:
            continue
        try:
            freq = int(m.group(1))
            band = freq_to_band(freq)
            if not band:
                continue
            mode = m.group(2).upper()
            if mode in ("PH", "SSB", "FM", "AM"):
                mode = "SSB"
            elif mode in ("RY", "RTTY", "FT8", "FT4", "DIGI"):
                mode = "DIGI"
            elif mode != "CW":
                mode = "CW"
            dt = datetime.strptime(f"{m.group(3)} {m.group(4)}", "%Y-%m-%d %H%M")
            qsos.append({
                "dt": dt,
                "utc_hour": dt.hour, "utc_min": dt.minute, "utc_month": dt.month,
                "band": band, "mode": mode,
                "freq": freq,
                "peer_call": m.group(8).upper(),
                "lineno": lineno,
            })
        except Exception:
            continue
    return qsos

def load_approx_grids(path):
    grids = {}
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            call = row["callsign"].strip().upper()
            g    = row["grid"].strip().upper()[:4]
            if call and GRID_RE.match(g):
                grids[call] = (
                    g,
                    row.get("power", "UNKNOWN").strip().upper(),
                    row.get("grid_source", "?"),
                )
    return grids

AMBIGUOUS = "AMBIGUOUS"

def try_match(call_a, qso_a, data_b, time_tol_min,
              band_override_a=None, band_override_b=None):
    call_a_norm = normalize_call(call_a)
    band_a = band_override_a or qso_a["band"]
    for qso_b in data_b["qsos"]:
        peer_b = qso_b["peer_call"]
        if peer_b != call_a:
            if normalize_call(peer_b) != call_a_norm:
                continue
            stroke_b = True
        else:
            stroke_b = False
        band_b = band_override_b or qso_b["band"]
        if band_b != band_a: continue
        if qso_b["mode"] != qso_a["mode"]: continue
        if abs((qso_b["dt"] - qso_a["dt"]).total_seconds()) / 60 > time_tol_min: continue
        return qso_b, stroke_b
    return None, False

def write_annotated_logs(logs, log_texts, annotations, out_dir, contest):
    ann_dir = out_dir / "annotated_approx" / contest
    ann_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    for call, data in logs.items():
        call_ann = annotations.get(call, {})
        if not call_ann:
            continue
        text = log_texts.get(call, "")
        lines = text.splitlines(keepends=True)
        out_lines = []
        for lineno, line in enumerate(lines):
            stripped = line.rstrip("\r\n")
            tag = call_ann.get(lineno)
            if tag:
                out_lines.append(stripped + tag + "\n")
            else:
                out_lines.append(line if line.endswith("\n") else line + "\n")
        fname = data["filename"]
        out_path = ann_dir / fname
        out_path.write_text("".join(out_lines), encoding="utf-8")
        written += 1
    print(msg(
        f"注釈ログ出力(approx): {written} ファイル → {ann_dir}",
        f"Annotated logs (approx) written: {written} file(s) → {ann_dir}",
    ))

def main():
    ap = argparse.ArgumentParser(
        description=msg(
            "approx版 Cabrillo QSOクロスチェック（cty.dat補完グリッド使用）",
            "approx Cabrillo QSO cross-check (cty.dat estimated grids)",
        )
    )
    ap.add_argument("--contest", required=True,
                    help=msg("コンテスト識別子 例: iaru, cqww_cw",
                             "Contest ID e.g.: iaru, cqww_cw"))
    ap.add_argument("--year", type=int, required=True,
                    help=msg("開催年 例: 2025", "Year e.g.: 2025"))
    ap.add_argument("--ssn", type=int, default=None)
    ap.add_argument("--raw-dir", default=None,
                    help=msg("ログファイルのディレクトリ", "Log file directory"))
    ap.add_argument("--out-dir", default=None,
                    help=msg("CSV出力先ルート", "CSV output root"))
    ap.add_argument("--approx-grids", default=None,
                    help=msg("approxグリッドDB（make_spotted_grids_approx.py出力）のパス",
                             "approx grid DB path (make_spotted_grids_approx.py output)"))
    ap.add_argument("--time-tol", type=int, default=15, metavar="MIN")
    ap.add_argument("--max-call-dist", type=int, default=3, metavar="N")
    ap.add_argument("--band-fix-window", type=int, default=10, metavar="MIN")
    ap.add_argument("--no-fuzzy", action="store_true")
    ap.add_argument("--no-band-fix", action="store_true")
    ap.add_argument("--annotate-logs", action="store_true",
                    help=msg("マッチ種別注釈付きログを annotated_approx/ に出力する",
                             "Write annotated logs to annotated_approx/"))
    args = ap.parse_args()

    _resolve_ssn = None
    _start_dt = None
    try:
        from contest_utils import (validate_contest, raw_log_dir, get_contest_dates,
                                   spotted_grids_approx_csv, qso_pairs_approx_csv,
                                   resolve_ssn as _resolve_ssn)
        validate_contest(args.contest)
        _raw_dir  = raw_log_dir(args.contest, args.year)
        _grids    = spotted_grids_approx_csv(args.contest, args.year)
        _out_csv  = qso_pairs_approx_csv(args.contest, args.year)
        _start_dt, _ = get_contest_dates(args.contest, args.year)
    except (ImportError, ValueError) as e:
        print(msg(f"警告: contest_utils未使用 ({e})",
                  f"Warning: contest_utils not available ({e})"))
        cid = f"{args.contest}_{args.year}"
        _script_dir = Path(__file__).resolve().parent
        _raw_dir = _script_dir/"raw"/cid
        _grids   = _script_dir/"rbn"/f"{cid}_spotted_grids_approx.csv"
        _out_csv = _script_dir/"csv"/f"{cid}_qso_pairs_approx.csv"

    raw_dir = Path(args.raw_dir)       if args.raw_dir      else _raw_dir
    grids_p = Path(args.approx_grids)  if args.approx_grids else _grids
    csv_dir = Path(args.out_dir)       if args.out_dir      else _out_csv.parent
    out_csv = csv_dir / _out_csv.name
    csv_dir.mkdir(parents=True, exist_ok=True)

    global TIME_TOL
    TIME_TOL = args.time_tol

    if not grids_p.exists():
        print(msg(f"エラー: approxグリッドDBが見つかりません: {grids_p}",
                  f"Error: approx grid DB not found: {grids_p}"))
        print(msg("  make_spotted_grids_approx.py を先に実行してください。",
                  "  Run make_spotted_grids_approx.py first."))
        return

    if _resolve_ssn:
        ssn = _resolve_ssn(args.contest, args.year,
                           ssn_override=args.ssn,
                           script_dir=Path(__file__).parent)
    else:
        ssn = args.ssn if args.ssn is not None else 0

    approx_grids = load_approx_grids(grids_p)
    print(msg(f"approxグリッドDB: {len(approx_grids)} 局",
              f"approx grid DB: {len(approx_grids)} stations"))

    log_files = sorted(raw_dir.glob("*.txt"))
    if not log_files:
        print(msg(f"エラー: ログなし: {raw_dir}",
                  f"Error: no logs found: {raw_dir}"))
        return
    print(msg(f"ログ数: {len(log_files)}", f"Log files: {len(log_files)}"))

    logs     = {}
    log_texts = {}

    for path in log_files:
        text   = path.read_text(encoding="utf-8", errors="replace")
        header = parse_header(text)
        call   = header.get("CALLSIGN", "").upper().strip()
        if not call or call not in approx_grids:
            continue
        grid, power, src = approx_grids[call]
        qsos = parse_qsos(text)
        if not qsos:
            continue
        logs[call] = {
            "grid": grid, "power": power, "qsos": qsos,
            "filename": path.name, "grid_source": src,
        }
        if args.annotate_logs:
            log_texts[call] = text

    print(msg(f"approxDBにありQSOあり: {len(logs)} 局",
              f"In approx DB with QSOs: {len(logs)} stations"))

    cty_stations = {c for c, d in logs.items() if d["grid_source"] != "log"}
    if not cty_stations:
        print(msg("cty.dat由来グリッドなし → マッチングをスキップ",
                  "No cty.dat-derived grids → skipping matching"))

    call_norm_to_raw = {}
    for raw_call in logs:
        norm = normalize_call(raw_call)
        call_norm_to_raw.setdefault(norm, []).append(raw_call)

    known_calls = list(logs.keys())

    def find_fuzzy_candidates(peer_call, max_dist):
        results = []
        peer_len = len(peer_call)
        for kc in known_calls:
            if len(kc) != peer_len: continue
            d = levenshtein(peer_call, kc)
            if 1 <= d <= max_dist:
                results.append((d, kc))
        results.sort()
        return results

    pairs     = []
    seen      = set()
    matched_qsos = set()
    annotations  = defaultdict(dict)

    stats = {
        "exact": 0, "stroke": 0,
        "fuzzy_by_dist": defaultdict(int),
        "band_fix_a": 0, "band_fix_b": 0, "band_fix_ambiguous": 0,
    }

    def add_annotation(call, lineno, tag):
        existing = annotations[call].get(lineno, "")
        if not existing:
            annotations[call][lineno] = "$" + tag
        elif tag.startswith("BANDFIX_AMBIGUOUS"):
            annotations[call][lineno] = existing + "," + tag

    def remove_ambiguous_annotation(call, lineno):
        if lineno not in annotations.get(call, {}):
            return
        raw = annotations[call][lineno]
        tags = [t for t in raw.lstrip("$").split(",")
                if not t.startswith("BANDFIX_AMBIGUOUS")]
        if tags:
            annotations[call][lineno] = "$" + ",".join(tags)
        else:
            del annotations[call][lineno]

    def is_cty(call):
        src = logs[call]["grid_source"] if call in logs else "log"
        return src != "log"

    def record_pair(call_a, data_a, qso_a,
                    call_b, data_b, qso_b,
                    call_dist, band_fix_tag,
                    orig_band_a=None, orig_band_b=None,
                    stroke_a=False, stroke_b=False):
        if not is_cty(call_a) and not is_cty(call_b):
            return False

        band_a_orig = orig_band_a if orig_band_a else qso_a["band"]
        band_b_orig = orig_band_b if orig_band_b else qso_b["band"]
        dt_pair = tuple(sorted([qso_a["dt"].strftime("%Y%m%d%H%M"),
                                qso_b["dt"].strftime("%Y%m%d%H%M")]))
        key = (tuple(sorted([call_a, call_b])),
               tuple(sorted([band_a_orig, band_b_orig])),
               qso_a["mode"], dt_pair)
        if key in seen:
            return False
        seen.add(key)
        matched_qsos.add((call_a, qso_a["lineno"]))
        matched_qsos.add((call_b, qso_b["lineno"]))
        if args.annotate_logs:
            remove_ambiguous_annotation(call_a, qso_a["lineno"])
            remove_ambiguous_annotation(call_b, qso_b["lineno"])

        lat_a, lon_a = grid_to_latlon(data_a["grid"])
        lat_b, lon_b = grid_to_latlon(data_b["grid"])
        if _start_dt is not None:
            utc_day = (qso_a["dt"].date() - _start_dt.date()).days
        else:
            utc_day = 0
        pairs.append({
            "grid_tx":     data_a["grid"],
            "grid_rx":     data_b["grid"],
            "band":        qso_a["band"],
            "mode":        qso_a["mode"],
            "utc_hour":    qso_a["utc_hour"],
            "utc_min":     qso_a["utc_min"],
            "utc_month":   qso_a["utc_month"],
            "utc_day":     utc_day,
            "distance_km": gcd_km(lat_a, lon_a, lat_b, lon_b),
            "ssn":         ssn,
            "tier":        1,
            "source":      args.contest,
            "lon_tx":      round(lon_a, 2),
            "power_tx":    data_a["power"],
            "power_rx":    data_b["power"],
            "call_dist":   call_dist,
            "band_fix":    band_fix_tag,
        })

        if not args.annotate_logs:
            return True

        tags_a = []
        if call_dist > 0:
            a_wrong = (qso_a["peer_call"] != call_b)
            peer_a_str = f"*{qso_a['peer_call']}" if a_wrong else qso_a["peer_call"]
            tags_a.append(f"FUZZY:{peer_a_str}(={call_b},dist={call_dist})")
        if orig_band_a:
            tags_a.append(f"BANDFIX:A(*{orig_band_a}->{qso_a['band']})")
        if stroke_a:
            tags_a.append(f"IGNORESTROKE({qso_a['peer_call']}->{call_b})")
        if tags_a:
            add_annotation(call_a, qso_a["lineno"], ",".join(tags_a))

        tags_b = []
        if call_dist > 0:
            b_wrong = (qso_b["peer_call"] != call_a)
            peer_b_str = f"*{qso_b['peer_call']}" if b_wrong else qso_b["peer_call"]
            tags_b.append(f"FUZZY:{peer_b_str}(={call_a},dist={call_dist})")
        if orig_band_b:
            tags_b.append(f"BANDFIX:B(*{orig_band_b}->{qso_b['band']})")
        if stroke_b:
            tags_b.append(f"IGNORESTROKE({qso_b['peer_call']}->{call_a})")
        if tags_b:
            add_annotation(call_b, qso_b["lineno"], ",".join(tags_b))

        return True

    print(msg("Pass 1: 完全マッチ処理中...", "Pass 1: exact matching..."))
    call_list = list(logs.items())

    for call_a, data_a in (call_list if cty_stations else []):
        for qi_a, qso_a in enumerate(data_a["qsos"]):
            peer = qso_a["peer_call"]
            stroke_a = False
            call_b = peer
            if peer not in logs:
                peer_norm = normalize_call(peer)
                candidates = call_norm_to_raw.get(peer_norm, [])
                if not candidates:
                    continue
                call_b = candidates[0]
                stroke_a = True
            data_b = logs[call_b]
            qso_b, stroke_b = try_match(call_a, qso_a, data_b, TIME_TOL)
            if qso_b:
                if record_pair(call_a, data_a, qso_a,
                               call_b, data_b, qso_b, 0, "",
                               stroke_a=stroke_a, stroke_b=stroke_b):
                    stats["exact"] += 1
                    if stroke_a or stroke_b:
                        stats["stroke"] += 1

    print(msg(
        f"  完全マッチ: {stats['exact']} ペア（うちストローク正規化: {stats['stroke']}）",
        f"  Exact match: {stats['exact']} pairs (stroke-normalized: {stats['stroke']})",
    ))
    print(msg("Pass 2: バンド訂正・曖昧マッチ処理中...",
              "Pass 2: band-fix and fuzzy matching..."))

    for call_a, data_a in (call_list if cty_stations else []):
        for qi_a, qso_a in enumerate(data_a["qsos"]):
            if (call_a, qso_a["lineno"]) in matched_qsos:
                continue

            peer = qso_a["peer_call"]
            _pending_ambiguous = []

            stroke_a_p2 = False
            call_b_p2   = peer
            if peer not in logs:
                _norm = normalize_call(peer)
                _cands = call_norm_to_raw.get(_norm, [])
                if _cands:
                    call_b_p2   = _cands[0]
                    stroke_a_p2 = True

            if call_b_p2 in logs:
                data_b = logs[call_b_p2]
                fixed = False

                if not args.no_band_fix:
                    window_sec = args.band_fix_window * 60
                    call_a_norm_p2 = normalize_call(call_a)

                    for qi_b, qso_b_cand in enumerate(data_b["qsos"]):
                        peer_b_raw = qso_b_cand["peer_call"]
                        if peer_b_raw != call_a:
                            if normalize_call(peer_b_raw) != call_a_norm_p2:
                                continue
                            stroke_b_cand = True
                        else:
                            stroke_b_cand = False
                        if (call_b_p2, qso_b_cand["lineno"]) in matched_qsos: continue
                        if qso_b_cand["mode"] != qso_a["mode"]: continue
                        if abs((qso_b_cand["dt"] - qso_a["dt"]).total_seconds()) / 60 > TIME_TOL: continue
                        if qso_b_cand["band"] == qso_a["band"]: continue

                        fix_side = None
                        correct_band = None

                        a_support = sum(
                            1 for j, o in enumerate(data_a["qsos"])
                            if j != qi_a and o["band"] == qso_a["band"]
                            and abs((o["dt"] - qso_a["dt"]).total_seconds()) <= window_sec
                        )
                        b_support = sum(
                            1 for j, o in enumerate(data_b["qsos"])
                            if j != qi_b and o["band"] == qso_b_cand["band"]
                            and abs((o["dt"] - qso_b_cand["dt"]).total_seconds()) <= window_sec
                        )

                        if a_support != b_support:
                            if b_support > a_support:
                                fix_side = "A"; correct_band = qso_b_cand["band"]
                            else:
                                fix_side = "B"; correct_band = qso_a["band"]
                        else:
                            a_round = (qso_a["freq"] % 1000 == 0)
                            b_round = (qso_b_cand["freq"] % 1000 == 0)
                            if a_round and not b_round:
                                fix_side = "A"; correct_band = qso_b_cand["band"]
                            elif b_round and not a_round:
                                fix_side = "B"; correct_band = qso_a["band"]
                            else:
                                stats["band_fix_ambiguous"] += 1
                                if args.annotate_logs:
                                    _pending_ambiguous.append(
                                        (call_a, qso_a["lineno"],
                                         f"BANDFIX_AMBIGUOUS:A(*{qso_a['band']}->{qso_b_cand['band']})"))

                        if fix_side is None: continue

                        if fix_side == "A":
                            orig_band_a = qso_a["band"]
                            qso_a["band"] = correct_band
                            if record_pair(call_a, data_a, qso_a,
                                           call_b_p2, data_b, qso_b_cand, 0, "A",
                                           orig_band_a=orig_band_a,
                                           stroke_a=stroke_a_p2, stroke_b=stroke_b_cand):
                                stats["band_fix_a"] += 1; fixed = True
                            qso_a["band"] = orig_band_a
                        else:
                            orig_band_b = qso_b_cand["band"]
                            qso_b_cand["band"] = correct_band
                            if record_pair(call_a, data_a, qso_a,
                                           call_b_p2, data_b, qso_b_cand, 0, "B",
                                           orig_band_b=orig_band_b,
                                           stroke_a=stroke_a_p2, stroke_b=stroke_b_cand):
                                stats["band_fix_b"] += 1; fixed = True
                            qso_b_cand["band"] = orig_band_b
                        if fixed: break

                if args.annotate_logs and not fixed:
                    for ac, al, at in _pending_ambiguous:
                        if (ac, al) not in matched_qsos:
                            add_annotation(ac, al, at)
                continue

            if args.no_fuzzy or args.max_call_dist == 0:
                if args.annotate_logs:
                    for ac, al, at in _pending_ambiguous:
                        if (ac, al) not in matched_qsos:
                            add_annotation(ac, al, at)
                continue

            matched_fuzzy = False
            candidates = find_fuzzy_candidates(peer, args.max_call_dist)
            for dist, call_b in candidates:
                data_b = logs[call_b]
                qso_b, stroke_b = try_match(call_a, qso_a, data_b, TIME_TOL)
                if qso_b:
                    if (call_b, qso_b["lineno"]) in matched_qsos:
                        continue
                    if record_pair(call_a, data_a, qso_a,
                                   call_b, data_b, qso_b, dist, "",
                                   stroke_b=stroke_b):
                        stats["fuzzy_by_dist"][dist] += 1
                    matched_fuzzy = True
                    break
            if args.annotate_logs and not matched_fuzzy:
                for ac, al, at in _pending_ambiguous:
                    if (ac, al) not in matched_qsos:
                        add_annotation(ac, al, at)

    fuzzy_total    = sum(stats["fuzzy_by_dist"].values())
    band_fix_total = stats["band_fix_a"] + stats["band_fix_b"]
    ambiguous_total = stats["band_fix_ambiguous"]
    total = len(pairs)

    print(msg(
        f"\napprox QSOペア（cty.dat由来グリッドを含むもの）: {total}",
        f"\napprox QSO pairs (includes cty.dat-derived grids): {total}",
    ))
    print(msg(f"使用SSN: {ssn}", f"SSN used: {ssn}"))
    print(msg("\n=== マッチ統計 ===", "\n=== Match statistics ==="))
    print(msg(f"  完全マッチ (dist=0):          {stats['exact']:6d}",
              f"  Exact match (dist=0):         {stats['exact']:6d}"))
    print(msg(f"    うちストローク正規化:         {stats['stroke']:6d}",
              f"    stroke-normalized:            {stats['stroke']:6d}"))
    for d in range(1, args.max_call_dist + 1):
        n = stats["fuzzy_by_dist"].get(d, 0)
        print(msg(f"  曖昧マッチ dist={d}:            {n:6d}",
                  f"  Fuzzy match dist={d}:           {n:6d}"))
    print(msg(f"  バンド訂正 (A側):             {stats['band_fix_a']:6d}",
              f"  Band fix (side A):            {stats['band_fix_a']:6d}"))
    print(msg(f"  バンド訂正 (B側):             {stats['band_fix_b']:6d}",
              f"  Band fix (side B):            {stats['band_fix_b']:6d}"))
    print(f"  ---")
    print(msg(
        f"  曖昧マッチ 小計:              {fuzzy_total:6d}"
        f"  ({fuzzy_total / max(1, total) * 100:.1f}%)",
        f"  Fuzzy match subtotal:         {fuzzy_total:6d}"
        f"  ({fuzzy_total / max(1, total) * 100:.1f}%)",
    ))
    print(msg(
        f"  バンド訂正 小計:              {band_fix_total:6d}"
        f"  ({band_fix_total / max(1, total) * 100:.1f}%)",
        f"  Band fix subtotal:            {band_fix_total:6d}"
        f"  ({band_fix_total / max(1, total) * 100:.1f}%)",
    ))
    print(msg(f"  合計:                         {total:6d}",
              f"  Total:                        {total:6d}"))

    if ambiguous_total > 0:
        print(msg(
            f"\n=== バンド訂正 AMBIGUOUS（同数のため訂正スキップ） ===",
            f"\n=== Band fix AMBIGUOUS (equal support — skipped) ===",
        ))
        print(msg(f"  件数: {ambiguous_total}", f"  Count: {ambiguous_total}"))

    fieldnames = [
        "grid_tx", "grid_rx", "band", "mode", "utc_hour", "utc_min", "utc_month",
        "utc_day", "distance_km", "ssn", "tier", "source", "lon_tx",
        "power_tx", "power_rx", "call_dist", "band_fix",
    ]
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(pairs)
    print(msg(f"\nCSV出力: {out_csv}", f"\nCSV written: {out_csv}"))

    for label_ja, label_en, key in [("バンド", "Band", "band"), ("モード", "Mode", "mode")]:
        print(msg(f"\n=== {label_ja}別 ===", f"\n=== By {label_en} ==="))
        for v, c in sorted(Counter(p[key] for p in pairs).items(), key=lambda x: -x[1]):
            print(f"  {v:6s}: {c:6d}")

    if args.annotate_logs:
        write_annotated_logs(logs, log_texts, annotations, csv_dir,
                             f"{args.contest}_{args.year}")

if __name__ == "__main__":
    main()
