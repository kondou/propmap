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

# ---------------------------------------------------------------------------
# contest_utils からのインポートを試みる（なければ内部実装を使用）
# ---------------------------------------------------------------------------
try:
    from contest_utils import get_contest_dates, rbn_raw_dir
    _use_utils = True
except ImportError:
    _use_utils = False

# ---------------------------------------------------------------------------
# コンテスト定義
# ---------------------------------------------------------------------------
RBN_CONTESTS = ["iaru", "cqww_cw", "cqwpx_cw"]

YEAR_RANGES = {
    "iaru":     range(2018, 2026),
    "cqww_cw":  range(2005, 2026),
    "cqwpx_cw": range(2008, 2026),
}

# ---------------------------------------------------------------------------
# 日程計算（contest_utils未使用時のフォールバック）
# ---------------------------------------------------------------------------
def _full_weekends(year, month):
    """指定月の全full weekend（土日が同月内）の土曜日リストを返す"""
    d = date(year, month, 1)
    while d.weekday() != 5:  # 5=土曜
        d += timedelta(days=1)
    results = []
    while d.month == month:
        if (d + timedelta(days=1)).month == month:  # 日曜も同月内
            results.append(d)
        d += timedelta(days=7)
    return results

def get_contest_dates_internal(contest, year):
    """コンテスト期間の日付リスト（dateオブジェクト）を返す"""
    if contest == "iaru":
        # 7月第2 full weekend 土〜日
        fws = _full_weekends(year, 7)
        sat = fws[1]
        return [sat, sat + timedelta(days=1)]
    elif contest == "cqww_cw":
        # 11月最終 full weekend
        sat = _full_weekends(year, 11)[-1]
        return [sat, sat + timedelta(days=1)]
    elif contest == "cqwpx_cw":
        # 5月最終 full weekend
        sat = _full_weekends(year, 5)[-1]
        return [sat, sat + timedelta(days=1)]
    else:
        raise ValueError(f"未知のコンテスト: {contest}")

def get_dates(contest, year):
    """コンテスト期間の日付リストを返す"""
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
    return Path.home() / "heatmap" / "contest_logs" / "rbn" / "raw"

# ---------------------------------------------------------------------------
# ダウンロード
# ---------------------------------------------------------------------------
RBN_BASE_URL = "https://www.reversebeacon.net/raw_data/dl.php?f="

def download_zip(date_obj, raw_dir, dry_run=False):
    """
    指定日付のRBN zipをダウンロードする。
    既存ファイルはスキップ。
    戻り値: 'downloaded' | 'skipped' | 'error'
    """
    fname = date_obj.strftime("%Y%m%d") + ".zip"
    dest = raw_dir / fname
    url = RBN_BASE_URL + date_obj.strftime("%Y%m%d")

    if dest.exists():
        print(f"  スキップ（既存）: {fname}")
        return "skipped"

    if dry_run:
        print(f"  [dry-run] ダウンロード予定: {fname}  ({url})")
        return "downloaded"

    print(f"  ダウンロード中: {fname} ...", end="", flush=True)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as resp, open(dest, "wb") as f:
            f.write(resp.read())
        size_kb = dest.stat().st_size // 1024
        print(f" {size_kb:,}KB")
        return "downloaded"
    except Exception as e:
        print(f" エラー: {e}")
        if dest.exists():
            dest.unlink()
        return "error"

def run(contests, years, dry_run=False):
    raw_dir = get_raw_dir()
    raw_dir.mkdir(parents=True, exist_ok=True)
    print(f"保存先: {raw_dir}")

    total_dl = total_skip = total_err = 0

    for contest in contests:
        for year in years:
            if year not in YEAR_RANGES.get(contest, range(2005, 2030)):
                continue
            try:
                dates = get_dates(contest, year)
            except Exception as e:
                print(f"[{contest} {year}] 日程取得エラー: {e}")
                continue

            print(f"\n[{contest} {year}] {dates[0]} 〜 {dates[-1]}")
            for d in dates:
                result = download_zip(d, raw_dir, dry_run=dry_run)
                if result == "downloaded":
                    total_dl += 1
                    if not dry_run:
                        time.sleep(1)  # サーバー負荷軽減
                elif result == "skipped":
                    total_skip += 1
                else:
                    total_err += 1

    print(f"\n完了: ダウンロード={total_dl}, スキップ={total_skip}, エラー={total_err}")

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="RBN生データ(zip)ダウンロード",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
例:
  python3 download_rbn.py --contest iaru --year 2025
  python3 download_rbn.py --contest cqww_cw --year 2024 2023
  python3 download_rbn.py --contest cqwpx_cw --all
  python3 download_rbn.py --all-contests --all
  python3 download_rbn.py --all-contests --all --dry-run
        """
    )
    parser.add_argument("--contest", choices=RBN_CONTESTS,
                        help="コンテスト識別子")
    parser.add_argument("--all-contests", action="store_true",
                        help="全RBN対象コンテストを対象にする")
    parser.add_argument("--year", type=int, nargs="+",
                        help="処理年（複数指定可）")
    parser.add_argument("--all", action="store_true",
                        help="全年を対象にする")
    parser.add_argument("--dry-run", action="store_true",
                        help="ダウンロードせず対象ファイルを表示のみ")
    args = parser.parse_args()

    if args.all_contests:
        contests = RBN_CONTESTS
    elif args.contest:
        contests = [args.contest]
    else:
        parser.error("--contest または --all-contests を指定してください")

    if args.all:
        years = sorted(set(
            y for c in contests for y in YEAR_RANGES.get(c, [])
        ))
    elif args.year:
        years = sorted(args.year)
    else:
        parser.error("--year または --all を指定してください")

    run(contests, years, dry_run=args.dry_run)

if __name__ == "__main__":
    main()
