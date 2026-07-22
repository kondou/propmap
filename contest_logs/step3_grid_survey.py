#!/usr/bin/env python3
"""
Step 3: グリッドロケーター含有状況の調査

使い方:
  python3 step3_grid_survey.py --contest iaru_2019
  python3 step3_grid_survey.py --raw-dir ~/heatmap/contest_logs/raw/cqww_cw_2024

入力:  ~/heatmap/contest_logs/raw/{contest}/*.txt
出力:  ~/heatmap/contest_logs/csv/{contest}_grid_survey.csv
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

GRID_FIELDS=["GRID-LOCATOR","HQ-GRID-LOCATOR","MY-GRIDSQUARE","LOCATION-GRID","GRID"]
GRID_RE=re.compile(r"^[A-R]{2}[0-9]{2}([A-X]{2})?$",re.IGNORECASE)

def parse_header(text):
    result={}
    for line in text.splitlines():
        if line.startswith("QSO:"): break
        m=re.match(r"^([A-Z0-9\-]+):\s*(.*)",line.strip(),re.IGNORECASE)
        if m: result[m.group(1).upper()]=m.group(2).strip()
    return result

def find_grid(header):
    for field in GRID_FIELDS:
        if field in header:
            parts = header[field].split()
            if not parts:
                continue
            val = parts[0]
            if GRID_RE.match(val): return field,val.upper()
    return None,None

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--contest",default=None,
                    help=msg("コンテスト識別子 例: iaru_2019",
                             "Contest ID e.g.: iaru_2019"))
    ap.add_argument("--raw-dir",default=None,
                    help=msg("ログファイルのディレクトリ", "Log file directory"))
    ap.add_argument("--out-dir",default=None)
    args=ap.parse_args()

    if args.raw_dir:
        raw_dir=Path(args.raw_dir)
        contest=raw_dir.name
    elif args.contest:
        contest=args.contest
        raw_dir=Path(__file__).resolve().parent/"raw"/contest
    else:
        ap.error(msg("--contest または --raw-dir を指定してください",
                     "Specify --contest or --raw-dir"))

    csv_dir=Path(args.out_dir) if args.out_dir else Path(__file__).resolve().parent/"csv"
    out_csv=csv_dir/f"{contest}_grid_survey.csv"
    csv_dir.mkdir(parents=True,exist_ok=True)

    log_files=sorted(raw_dir.glob("*.txt"))
    if not log_files:
        print(msg(f"ファイルなし: {raw_dir}", f"No files found: {raw_dir}")); return
    print(msg(f"対象: {len(log_files)} ファイル",
              f"Target: {len(log_files)} files"))

    rows=[]; counts={"6char":0,"4char":0,"none":0,"other":0}
    for path in log_files:
        text=path.read_text(encoding="utf-8",errors="replace")
        header=parse_header(text)
        gf,gv=find_grid(header)
        qso_count=sum(1 for l in text.splitlines() if l.startswith("QSO:"))
        gc="none" if gv is None else ("6char" if len(gv)>=6 else "4char" if len(gv)==4 else "other")
        counts[gc]+=1
        rows.append({"filename":path.name,"callsign":header.get("CALLSIGN",""),
                     "category_power":header.get("CATEGORY-POWER",""),
                     "category_op":header.get("CATEGORY-OPERATOR",""),
                     "category_band":header.get("CATEGORY-BAND",""),
                     "category_mode":header.get("CATEGORY-MODE",""),
                     "grid_field":gf or "","grid_value":gv or "",
                     "grid_chars":gc,"qso_count":qso_count,
                     "created_by":header.get("CREATED-BY","")})

    fieldnames=["filename","callsign","category_power","category_op","category_band",
                "category_mode","grid_field","grid_value","grid_chars","qso_count","created_by"]
    with open(out_csv,"w",newline="",encoding="utf-8") as f:
        csv.DictWriter(f,fieldnames=fieldnames).writeheader()
        csv.DictWriter(f,fieldnames=fieldnames).writerows(rows)

    total=len(rows)
    print(msg("\n=== グリッド含有状況 ===", "\n=== Grid locator presence ==="))
    for k,v in counts.items():
        print(f"  {k:8s}: {v:5d} ({v/total*100:.1f}%)")
    print(msg(f"\nCSV出力: {out_csv}", f"\nCSV written: {out_csv}"))

    from collections import Counter
    sw_stats=Counter(r["created_by"][:30] or "(unknown)" for r in rows)
    sw_grid=Counter()
    for r in rows:
        if r["grid_value"]: sw_grid[r["created_by"][:30] or "(unknown)"]+=1
    print(msg("\n=== ソフト別グリッド含有率 (上位10) ===",
              "\n=== Grid presence by logging software (top 10) ==="))
    for sw,total_sw in sw_stats.most_common(10):
        g=sw_grid[sw]
        print(f"  {sw:<32s} {g:4d}/{total_sw:4d} ({g/total_sw*100:5.1f}%)")

if __name__=="__main__":
    main()
