#!/usr/bin/env python3
"""
download_rbn.py - RBN生データ(zip)ダウンロードスクリプト

使用例:
  python3 download_rbn.py --contest iaru --year 2025
  python3 download_rbn.py --contest cqww_cw --year 2024 2023
  python3 download_rbn.py --contest cqwpx_cw --all
  python3 download_rbn.py --all-contests --all
  python3 download_rbn.py --all-contests --all --dry-run
"""

import argparse
import sys
import os
import time
import urllib.request
from datetime import date, timedelta
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

try:
    from contest_utils import (get_contest_dates, rbn_raw_dir,
                               available_years, CONTEST_CFG)
    _use_utils = True
except ImportError:
    _use_utils = False

# 一次情報は contest_utils（has_rbn フラグと available_years）。
# import 失敗時のみ静的フォールバック。
if _use_utils:
    RBN_CONTESTS = [c for c, cfg in CONTEST_CFG.items() if cfg["has_rbn"]]
    YEAR_RANGES  = {c: available_years(c) for c in RBN_CONTESTS}
else:
    RBN_CONTESTS = ["iaru", "cqww_cw", "cqwpx_cw"]
    YEAR_RANGES = {
        "iaru":     range(2018, 2026),
        "cqww_cw":  range(2005, 2026),
        "cqwpx_cw": range(2008, 2026),
    }

def _full_weekends(year, month):
    d = date(year, month, 1)
    while d.weekday() != 5:
        d += timedelta(days=1)
    results = []
    while d.month == month:
        if (d + timedelta(days=1)).month == month:
            results.append(d)
        d += timedelta(days=7)
    return results

def get_contest_dates_internal(contest, year):
    if contest == "iaru":
        fws = _full_weekends(year, 7)
        sat = fws[1]
        return [sat, sat + timedelta(days=1)]
    elif contest == "cqww_cw":
        sat = _full_weekends(year, 11)[-1]
        return [sat, sat + timedelta(days=1)]
    elif contest == "cqwpx_cw":
        sat = _full_weekends(year, 5)[-1]
        return [sat, sat + timedelta(days=1)]
    else:
        raise ValueError(msg(f"未知のコンテスト: {contest}",
                             f"Unknown contest: {contest}"))

def get_dates(contest, year):
    if _use_utils:
        try:
            start, end = get_contest_dates(contest, year)
            dates = []
            d = start.date() if hasattr(start, 'date') else start
            e = end.date() if hasattr(end, 'date') else end
            while d <= e:
                dates.append(d)
                d += timedelta(days=1)
            return dates
        except Exception:
            pass
    return get_contest_dates_internal(contest, year)

def get_raw_dir():
    if _use_utils:
        try:
            return Path(rbn_raw_dir())
        except Exception:
            pass
    return Path(__file__).resolve().parent / "rbn" / "raw"

RBN_BASE_URL = "https://www.reversebeacon.net/raw_data/dl.php?f="

def download_zip(date_obj, raw_dir, dry_run=False):
    fname = date_obj.strftime("%Y%m%d") + ".zip"
    dest = raw_dir / fname
    url = RBN_BASE_URL + date_obj.strftime("%Y%m%d")

    if dest.exists():
        print(msg(f"  スキップ（既存）: {fname}",
                  f"  Skipped (exists): {fname}"))
        return "skipped"

    if dry_run:
        print(msg(f"  [dry-run] ダウンロード予定: {fname}  ({url})",
                  f"  [dry-run] Would download: {fname}  ({url})"))
        return "downloaded"

    print(msg(f"  ダウンロード中: {fname} ...",
              f"  Downloading: {fname} ..."), end="", flush=True)
    # 中断時に壊れたzipを「完了」として残さないよう、.partに書いてから
    # rename する（rename前は dest が存在しないため、再実行時は正しく
    # 再ダウンロード対象になる）
    part = dest.with_suffix(dest.suffix + ".part")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as resp, open(part, "wb") as f:
            f.write(resp.read())
        part.replace(dest)
        size_kb = dest.stat().st_size // 1024
        print(f" {size_kb:,}KB")
        return "downloaded"
    except Exception as e:
        print(msg(f" エラー: {e}", f" Error: {e}"))
        if part.exists():
            part.unlink()
        return "error"

def run(contests, years, dry_run=False):
    raw_dir = get_raw_dir()
    raw_dir.mkdir(parents=True, exist_ok=True)
    print(msg(f"保存先: {raw_dir}", f"Save dir: {raw_dir}"))

    total_dl = total_skip = total_err = 0

    for contest in contests:
        for year in years:
            if year not in YEAR_RANGES.get(contest, range(2005, 2030)):
                continue
            try:
                dates = get_dates(contest, year)
            except Exception as e:
                print(msg(f"[{contest} {year}] 日程取得エラー: {e}",
                          f"[{contest} {year}] Failed to get dates: {e}"))
                continue

            print(msg(f"\n[{contest} {year}] {dates[0]} 〜 {dates[-1]}",
                      f"\n[{contest} {year}] {dates[0]} to {dates[-1]}"))
            for d in dates:
                result = download_zip(d, raw_dir, dry_run=dry_run)
                if result == "downloaded":
                    total_dl += 1
                    if not dry_run:
                        time.sleep(1)
                elif result == "skipped":
                    total_skip += 1
                else:
                    total_err += 1

    print(msg(f"\n完了: ダウンロード={total_dl}, スキップ={total_skip}, エラー={total_err}",
              f"\nDone: downloaded={total_dl}, skipped={total_skip}, errors={total_err}"))

def main():
    parser = argparse.ArgumentParser(
        description=msg("RBN生データ(zip)ダウンロード",
                        "Download RBN raw data (zip)"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=msg(
            "例:\n"
            "  python3 download_rbn.py --contest iaru --year 2025\n"
            "  python3 download_rbn.py --contest cqww_cw --year 2024 2023\n"
            "  python3 download_rbn.py --contest cqwpx_cw --all\n"
            "  python3 download_rbn.py --all-contests --all\n"
            "  python3 download_rbn.py --all-contests --all --dry-run",
            "Examples:\n"
            "  python3 download_rbn.py --contest iaru --year 2025\n"
            "  python3 download_rbn.py --contest cqww_cw --year 2024 2023\n"
            "  python3 download_rbn.py --contest cqwpx_cw --all\n"
            "  python3 download_rbn.py --all-contests --all\n"
            "  python3 download_rbn.py --all-contests --all --dry-run",
        )
    )
    parser.add_argument("--contest", choices=RBN_CONTESTS,
                        help=msg("コンテスト識別子", "Contest ID"))
    parser.add_argument("--all-contests", action="store_true",
                        help=msg("全RBN対象コンテストを対象にする",
                                 "Process all RBN-enabled contests"))
    parser.add_argument("--year", type=int, nargs="+",
                        help=msg("処理年（複数指定可）", "Year(s) to process"))
    parser.add_argument("--all", action="store_true",
                        help=msg("全年を対象にする", "Process all available years"))
    parser.add_argument("--dry-run", action="store_true",
                        help=msg("ダウンロードせず対象ファイルを表示のみ",
                                 "Show files to download without downloading"))
    args = parser.parse_args()

    if args.all_contests:
        contests = RBN_CONTESTS
    elif args.contest:
        contests = [args.contest]
    else:
        parser.error(msg("--contest または --all-contests を指定してください",
                         "Specify --contest or --all-contests"))

    if args.all:
        years = sorted(set(
            y for c in contests for y in YEAR_RANGES.get(c, [])
        ))
    elif args.year:
        years = sorted(args.year)
    else:
        parser.error(msg("--year または --all を指定してください",
                         "Specify --year or --all"))

    run(contests, years, dry_run=args.dry_run)

if __name__ == "__main__":
    main()
