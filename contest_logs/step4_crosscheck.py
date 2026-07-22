#!/usr/bin/env python3
"""
Step 4: グリッドあり局同士のQSOクロスチェック（曖昧マッチ・バンド訂正対応版）

使い方:
  python3 step4_crosscheck.py --contest iaru --year 2025
  python3 step4_crosscheck.py --contest cqww_cw --year 2024 \
      --max-call-dist 2 --band-fix-window 15 --annotate-logs
  python3 step4_crosscheck.py --contest iaru --year 2025 --ssn 68  # 手動上書き可

入力:  ~/heatmap/contest_logs/raw/{contest}_{year}/*.txt
出力:  ~/heatmap/contest_logs/csv/{contest}_{year}_qso_pairs.csv
       ~/heatmap/contest_logs/csv/annotated/{contest}_{year}/*.txt  (--annotate-logs 時のみ)

処理内容:
  1. グリッドロケーターが有効なログのみ対象
  2. 各ログのQSO行をパース（相手コールサイン・バンド・モード・UTC）
  3. 相手局のログも存在し、かつそちらにもグリッドがある場合にペアとして記録
  4. 時刻の照合: 同一バンド・モードで±time-tol分以内をマッチとする
  5. 出力にはコールサインを含まず、グリッド・バンド・モード・UTC時間・距離のみ
  6. [拡張] 曖昧コールサインマッチ: レーベンシュタイン距離1〜max_call_distで段階的検索
     完全マッチ優先・距離が近いペアが優先。ダブりは最小距離のペアのみ採用。
  7. [拡張] バンド訂正: 前後band_fix_window分以内のQSOのバンド多数決により、
     自バンドより他バンドのQSOが多い場合は訂正してマッチを試みる。
     自バンドと他バンドが同数の場合はAMBIGUOUSとしてスキップ（終了時に件数報告）。
     SO2R・マルチオペ対応: バンドが飛ぶこと自体は誤記録とみなさない。
  8. [拡張] --annotate-logs: 曖昧マッチ・バンド訂正でマッチしたQSO行に
     $FUZZY:実コール(dist=N) / $BANDFIX:側(誤→正) を末尾付加したログを出力。
     注釈のある行が1件以上あるファイルのみ出力。
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
GRID_FIELDS = ["GRID-LOCATOR","HQ-GRID-LOCATOR","MY-GRIDSQUARE","LOCATION-GRID","GRID"]
TIME_TOL    = 15  # マッチ許容時間差（分）デフォルト、--time-tolで変更可

# /QRP /MM /AM /P /M /数字 サフィックスを除去して基本コールを得る
_STROKE_RE = re.compile(r'^(.+)/(?:QRP|MM|AM|P|M|\d)$', re.IGNORECASE)
def normalize_call(cs):
    m = _STROKE_RE.match(cs.upper().strip())
    return m.group(1) if m else cs.upper().strip()

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

# ---------------------------------------------------------------------------
# レーベンシュタイン距離
# ---------------------------------------------------------------------------
def levenshtein(a, b):
    if a == b:
        return 0
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i]
        for j, cb in enumerate(b, 1):
            curr.append(min(prev[j] + 1, curr[j-1] + 1, prev[j-1] + (ca != cb)))
        prev = curr
    return prev[-1]

# ---------------------------------------------------------------------------
# ユーティリティ
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# ログパース
# ---------------------------------------------------------------------------
def parse_header(text):
    result = {}
    for line in text.splitlines():
        if line.upper().startswith("QSO:"):
            break
        m = re.match(r"^([A-Z0-9\-]+):\s*(.*)", line.strip(), re.IGNORECASE)
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

def parse_qsos(text):
    """QSOリストと、各QSOが元テキストの何行目(0-based)にあるかを返す"""
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
                "freq": freq,           # 周波数（バンド信頼性判定用）
                "peer_call": m.group(8).upper(),
                "lineno": lineno,       # 元テキスト行番号（注釈付加用）
            })
        except:
            continue
    return qsos

AMBIGUOUS = "AMBIGUOUS"  # 訂正候補が同数で決定不能

# ---------------------------------------------------------------------------
# マッチング補助
# ---------------------------------------------------------------------------
def try_match(call_a, qso_a, data_b, time_tol_min,
              band_override_a=None, band_override_b=None):
    """qso_a に対して data_b の中からマッチするQSOを返す。
    ストローク正規化も試みる。戻り値: (qso_b or None, stroke_b: bool)"""
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
        if band_b != band_a:
            continue
        if qso_b["mode"] != qso_a["mode"]:
            continue
        if abs((qso_b["dt"] - qso_a["dt"]).total_seconds()) / 60 > time_tol_min:
            continue
        return qso_b, stroke_b
    return None, False

# ---------------------------------------------------------------------------
# 注釈付きログ出力
# ---------------------------------------------------------------------------
def write_annotated_logs(logs, log_texts, annotations, out_dir, contest,
                         subdir="annotated"):
    """
    annotations: {call: {lineno: "$TAG,..."}}
    注釈がある行を1件以上含むファイルのみ出力。
    subdir: 出力サブディレクトリ名（approx版は "annotated_approx" を指定）
    """
    ann_dir = out_dir / subdir / contest
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
        f"注釈ログ出力: {written} ファイル → {ann_dir}",
        f"Annotated logs written: {written} file(s) → {ann_dir}",
    ))

# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(
        description=msg(
            "Cabrillo QSOクロスチェック（曖昧マッチ・バンド訂正対応）",
            "Cabrillo QSO cross-check (fuzzy match + band correction)",
        )
    )
    ap.add_argument("--contest", required=True,
                    help=msg("コンテスト識別子 例: iaru, cqww_cw, cqwpx_ssb",
                             "Contest ID e.g.: iaru, cqww_cw, cqwpx_ssb"))
    ap.add_argument("--year", type=int, required=True,
                    help=msg("開催年 例: 2025", "Year e.g.: 2025"))
    ap.add_argument("--ssn", type=int, default=None,
                    help=msg("開催月の月平均SSN（省略時: SN_m_tot_V2.0.txt から自動取得）",
                             "Monthly SSN (default: auto from SN_m_tot_V2.0.txt)"))
    ap.add_argument("--raw-dir", default=None,
                    help=msg("ログファイルのディレクトリ",
                             "Log file directory"))
    ap.add_argument("--out-dir", default=None,
                    help=msg("CSV・注釈ログ出力先ルート",
                             "CSV / annotated log output root"))
    ap.add_argument("--time-tol", type=int, default=15, metavar="MIN",
                    help=msg("QSO時刻マッチの許容誤差（分） (デフォルト: 15)",
                             "QSO time match tolerance in minutes (default: 15)"))
    ap.add_argument("--max-call-dist", type=int, default=3, metavar="N",
                    help=msg("曖昧コールサインマッチの最大レーベンシュタイン距離 (デフォルト: 3)",
                             "Max Levenshtein distance for fuzzy callsign match (default: 3)"))
    ap.add_argument("--band-fix-window", type=int, default=10, metavar="MIN",
                    help=msg("バンド訂正判定の前後時間窓（分） (デフォルト: 10)",
                             "Band-fix judgment window in minutes (default: 10)"))
    ap.add_argument("--no-fuzzy", action="store_true",
                    help=msg("曖昧マッチを無効化（完全マッチのみ）",
                             "Disable fuzzy match (exact match only)"))
    ap.add_argument("--no-band-fix", action="store_true",
                    help=msg("バンド訂正を無効化", "Disable band correction"))
    ap.add_argument("--annotate-logs", action="store_true",
                    help=msg("曖昧マッチ・バンド訂正の注釈付きログを出力する",
                             "Write annotated logs for fuzzy/band-fix matches"))
    args = ap.parse_args()

    # contest_utilsでパス解決
    _resolve_ssn = None
    _start_dt = None
    try:
        from contest_utils import validate_contest, raw_log_dir, qso_pairs_csv, resolve_ssn as _resolve_ssn, get_contest_dates
        validate_contest(args.contest)
        _raw_dir = raw_log_dir(args.contest, args.year)
        _out_csv = qso_pairs_csv(args.contest, args.year)
        _start_dt, _ = get_contest_dates(args.contest, args.year)
    except (ImportError, ValueError) as e:
        print(msg(f"警告: contest_utils未使用 ({e})",
                  f"Warning: contest_utils not available ({e})"))
        _script_dir = Path(__file__).resolve().parent
        _raw_dir = _script_dir / "raw" / f"{args.contest}_{args.year}"
        _out_csv = _script_dir / "csv" / f"{args.contest}_{args.year}_qso_pairs.csv"

    raw_dir = Path(args.raw_dir) if args.raw_dir else _raw_dir
    csv_dir = Path(args.out_dir) if args.out_dir else _out_csv.parent
    out_csv = csv_dir / _out_csv.name if not args.out_dir else csv_dir / _out_csv.name
    csv_dir.mkdir(parents=True, exist_ok=True)

    # SSN解決（contest_utils.resolve_ssn を優先、未使用時はSSN=0）
    if _resolve_ssn:
        ssn = _resolve_ssn(args.contest, args.year,
                           ssn_override=args.ssn,
                           script_dir=Path(__file__).parent)
    else:
        ssn = args.ssn if args.ssn is not None else 0
        if ssn == 0:
            print(msg("警告: contest_utils未使用のためSSN=0を使用します。",
                      "Warning: contest_utils not available; using SSN=0."))

    # TIME_TOLをオプション値で上書き
    global TIME_TOL
    TIME_TOL = args.time_tol

    log_files = sorted(raw_dir.glob("*.txt"))
    if not log_files:
        print(msg(f"ログファイルが見つかりません: {raw_dir}",
                  f"No log files found: {raw_dir}"))
        return
    print(msg(f"ログファイル数: {len(log_files)}",
              f"Log files: {len(log_files)}"))

    # ---- ログ読み込み -------------------------------------------------------
    logs = {}
    log_texts = {}  # call → 元テキスト（注釈出力用）
    for path in log_files:
        text = path.read_text(encoding="utf-8", errors="replace")
        header = parse_header(text)
        call = header.get("CALLSIGN", "").upper()
        if not call:
            continue
        grid = get_grid(header)
        if not grid:
            continue
        power = header.get("CATEGORY-POWER", "UNKNOWN").upper()
        if power not in ("HIGH", "LOW", "QRP"):
            power = "UNKNOWN"
        qsos = parse_qsos(text)
        if not qsos:
            continue
        logs[call] = {
            "grid": grid, "power": power, "qsos": qsos,
            "filename": path.name,
        }
        if args.annotate_logs:
            log_texts[call] = text

    print(msg(f"グリッドあり有効ログ: {len(logs)} 局",
              f"Valid logs with grid: {len(logs)} stations"))

    # ---- ストローク正規化インデックス ----------------------------------------
    call_norm_to_raw = {}
    for raw_call in logs:
        norm = normalize_call(raw_call)
        call_norm_to_raw.setdefault(norm, []).append(raw_call)

    # ---- 曖昧マッチ用インデックス -------------------------------------------
    known_calls = list(logs.keys())

    def find_fuzzy_candidates(peer_call, max_dist):
        results = []
        peer_len = len(peer_call)
        for kc in known_calls:
            if len(kc) != peer_len:
                continue
            d = levenshtein(peer_call, kc)
            if 1 <= d <= max_dist:
                results.append((d, kc))
        results.sort()
        return results

    # ---- マッチング ---------------------------------------------------------
    pairs = []
    seen = set()
    matched_qsos = set()
    annotations = defaultdict(dict)

    stats = {
        "exact": 0,
        "stroke": 0,
        "fuzzy_by_dist": defaultdict(int),
        "band_fix_a": 0,
        "band_fix_b": 0,
        "band_fix_ambiguous": 0,
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

    def record_pair(call_a, data_a, qso_a,
                    call_b, data_b, qso_b,
                    call_dist, band_fix_tag,
                    orig_band_a=None, orig_band_b=None,
                    stroke_a=False, stroke_b=False):
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

    print(msg("Pass 1: 完全マッチ処理中...",
              "Pass 1: exact matching..."))
    call_list = list(logs.items())

    for call_a, data_a in call_list:
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

    for call_a, data_a in call_list:
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
                        if (call_b_p2, qso_b_cand["lineno"]) in matched_qsos:
                            continue
                        if qso_b_cand["mode"] != qso_a["mode"]:
                            continue
                        if abs((qso_b_cand["dt"] - qso_a["dt"]).total_seconds()) / 60 > TIME_TOL:
                            continue
                        if qso_b_cand["band"] == qso_a["band"]:
                            continue

                        fix_side = None
                        correct_band = None

                        a_support = sum(
                            1 for j, o in enumerate(data_a["qsos"])
                            if j != qi_a
                            and o["band"] == qso_a["band"]
                            and abs((o["dt"] - qso_a["dt"]).total_seconds()) <= window_sec
                        )
                        b_support = sum(
                            1 for j, o in enumerate(data_b["qsos"])
                            if j != qi_b
                            and o["band"] == qso_b_cand["band"]
                            and abs((o["dt"] - qso_b_cand["dt"]).total_seconds()) <= window_sec
                        )

                        if a_support != b_support:
                            if b_support > a_support:
                                fix_side = "A"
                                correct_band = qso_b_cand["band"]
                            else:
                                fix_side = "B"
                                correct_band = qso_a["band"]
                        else:
                            a_round = (qso_a["freq"] % 1000 == 0)
                            b_round = (qso_b_cand["freq"] % 1000 == 0)
                            if a_round and not b_round:
                                fix_side = "A"
                                correct_band = qso_b_cand["band"]
                            elif b_round and not a_round:
                                fix_side = "B"
                                correct_band = qso_a["band"]
                            else:
                                stats["band_fix_ambiguous"] += 1
                                if args.annotate_logs:
                                    _pending_ambiguous.append(
                                        (call_a, qso_a["lineno"],
                                         f"BANDFIX_AMBIGUOUS:A(*{qso_a['band']}->{qso_b_cand['band']})"))

                        if fix_side is None:
                            continue

                        if fix_side == "A":
                            orig_band_a = qso_a["band"]
                            qso_a["band"] = correct_band
                            if record_pair(call_a, data_a, qso_a,
                                           call_b_p2, data_b, qso_b_cand, 0, "A",
                                           orig_band_a=orig_band_a,
                                           stroke_a=stroke_a_p2, stroke_b=stroke_b_cand):
                                stats["band_fix_a"] += 1
                                fixed = True
                            qso_a["band"] = orig_band_a
                        else:
                            orig_band_b = qso_b_cand["band"]
                            qso_b_cand["band"] = correct_band
                            if record_pair(call_a, data_a, qso_a,
                                           call_b_p2, data_b, qso_b_cand, 0, "B",
                                           orig_band_b=orig_band_b,
                                           stroke_a=stroke_a_p2, stroke_b=stroke_b_cand):
                                stats["band_fix_b"] += 1
                                fixed = True
                            qso_b_cand["band"] = orig_band_b
                        if fixed:
                            break

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

    # ---- 統計表示 -----------------------------------------------------------
    fuzzy_total = sum(stats["fuzzy_by_dist"].values())
    band_fix_total = stats["band_fix_a"] + stats["band_fix_b"]
    ambiguous_total = stats["band_fix_ambiguous"]
    total = len(pairs)

    print(msg(f"\nクロスチェック済みQSOペア: {total}",
              f"\nCross-checked QSO pairs: {total}"))
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
        print(msg(
            f"  ※ これらのQSOはバンド訂正を試みましたが前後window内で\n"
            f"    自バンドと候補バンドのQSO数が同数だったため訂正不可でした。\n"
            f"    --band-fix-window を広げるか、該当ログを手動確認してください。",
            f"  These QSOs could not be band-corrected because support counts\n"
            f"  were equal within the window. Widen --band-fix-window or\n"
            f"  inspect the logs manually.",
        ))

    # ---- CSV出力 ------------------------------------------------------------
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

    # ---- バンド・モード別統計 -----------------------------------------------
    for label_ja, label_en, key in [
        ("バンド", "Band", "band"),
        ("モード", "Mode", "mode"),
    ]:
        print(msg(f"\n=== {label_ja}別 ===", f"\n=== By {label_en} ==="))
        for v, c in sorted(Counter(p[key] for p in pairs).items(),
                           key=lambda x: -x[1]):
            print(f"  {v:6s}: {c:6d}")

    if fuzzy_total > 0:
        print(msg(f"\n=== 曖昧マッチ内訳（dist別・バンド別） ===",
                  f"\n=== Fuzzy match breakdown (by dist / band) ==="))
        for d in range(1, args.max_call_dist + 1):
            sub = [p for p in pairs if p["call_dist"] == d]
            if not sub:
                continue
            print(msg(f"  dist={d} ({len(sub)}件)", f"  dist={d} ({len(sub)} pairs)"))
            for v, c in sorted(Counter(p["band"] for p in sub).items(),
                               key=lambda x: -x[1]):
                print(f"    {v:6s}: {c:4d}")

    if band_fix_total > 0:
        print(msg(f"\n=== バンド訂正内訳 ===", f"\n=== Band fix breakdown ==="))
        for side_ja, side_en, tag in [
            ("A側", "Side A", "A"),
            ("B側", "Side B", "B"),
        ]:
            sub = [p for p in pairs if p["band_fix"] == tag]
            if not sub:
                continue
            print(msg(f"  {side_ja}訂正 ({len(sub)}件) バンド別:",
                      f"  {side_en} fix ({len(sub)} pairs) by band:"))
            for v, c in sorted(Counter(p["band"] for p in sub).items(),
                               key=lambda x: -x[1]):
                print(f"    {v:6s}: {c:4d}")

    # ---- 注釈ログ出力 -------------------------------------------------------
    if args.annotate_logs:
        write_annotated_logs(logs, log_texts, annotations, csv_dir,
                             f"{args.contest}_{args.year}")

if __name__ == "__main__":
    main()
