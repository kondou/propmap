#!/usr/bin/env python3
"""
check_new_logs.py - 新規開催年の公開ログ/RBNデータの有無確認と取り込み

流れ:
  1. contest_utils の開催日程から「ローカル未保持の新しい年」を列挙
  2. 公開ログサイトを確認し、公開されていれば件数を取得
  3. ダウンロードサイズ / RBNサイズ / JSON変換後サイズを推定して合計表示
  4. 空き容量を確認のうえ y/n プロンプト → step1〜step5 を一気通貫実行

使用例:
  python3 check_new_logs.py                     # 確認と見積もりのみ（対話で実行可）
  python3 check_new_logs.py --dry-run           # 見積もり表示のみで終了
  python3 check_new_logs.py --contest cqwpx_cw  # 対象コンテストを限定
  python3 check_new_logs.py --yes               # 確認プロンプトをスキップ
  python3 check_new_logs.py --all-missing       # 過去の未保持年もすべて対象にする

備考:
  - 「新しい年」= ローカル raw/{contest}_{year}/ に存在する最新年より後の開催済み年。
    差し替え（既存年の再公開）は検出しない。
  - RBN raw zip はダウンロード後もzipのまま保持され、JSON生成時に一時展開される
    （既存パイプラインの挙動を踏襲）。
"""

import argparse
import re
import shutil
import subprocess
import sys
import urllib.request
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from contest_utils import (msg, CONTEST_CFG, BASE_DIR, HEATMAP_DIR,
                           available_years, get_rbn_dates, raw_log_dir,
                           rbn_raw_dir, qso_json, rbn_json,
                           qso_approx_json, rbn_approx_json)

SCRIPT_DIR = Path(__file__).parent
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"}

RBN_BASE_URL = "https://www.reversebeacon.net/raw_data/dl.php?f="

# 公開ログ平均サイズのフォールバック値（ローカル実測がない場合）
DEFAULT_AVG_LOG_BYTES = 40 * 1024


# ---- HTTP -------------------------------------------------------------------

def http_get(url: str, timeout: int = 25) -> str | None:
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            for enc in ("utf-8", "latin-1", "cp1252"):
                try:
                    return raw.decode(enc)
                except Exception:
                    pass
            return raw.decode("utf-8", errors="replace")
    except Exception:
        return None


def http_head_size(url: str, timeout: int = 25) -> int | None:
    """HEADで Content-Length を取得。取得不能なら None。"""
    req = urllib.request.Request(url, headers=HEADERS, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            cl = r.headers.get("Content-Length")
            return int(cl) if cl and int(cl) > 0 else None
    except Exception:
        return None


# ---- 公開ログサイトの確認 ---------------------------------------------------

_CQDIR_LINK_RE = re.compile(r'href="([^"]+\.(?:log|cbr|txt))"', re.IGNORECASE)
_ARRL_LOG_RE   = re.compile(r'showpubliclog\.php', re.IGNORECASE)
_ARRL_COUNT_RE = re.compile(
    r'Number of logs found[^:]*:\s*([\d,]+)', re.IGNORECASE)
_ARRL_YEAR_LINK_RE = re.compile(
    r'href="(?:https?://contests\.arrl\.org/)?publiclogs\.php\?eid=4&(?:amp;)?iid=(\d+)"[^>]*>\s*(\d{4})\s*<',
    re.IGNORECASE)

# 既知の IARU 年別 iid（step1_collect_logs_fast.py と同じキャッシュ）
IARU_YEAR_URLS = {
    2025: "https://contests.arrl.org/publiclogs.php?eid=4&iid=1110",
}


def cqdir_list_url(contest: str, year: int) -> str:
    suffix = "cw" if contest.endswith("_cw") else "ph"
    site = "cqww.com" if contest.startswith("cqww") else "cqwpx.com"
    return f"https://{site}/publiclogs/{year}{suffix}/"


def probe_public_logs(contest: str, year: int) -> int | None:
    """
    公開ログの有無を確認し、公開されていればログ件数を返す。
    未公開・確認不能なら None。
    """
    if contest == "iaru":
        url = IARU_YEAR_URLS.get(year)
        if url is None:
            # 既知ページから年→iidリンクをスクレイプして解決
            seed = IARU_YEAR_URLS[max(IARU_YEAR_URLS)]
            html = http_get(seed)
            if html:
                for iid, y in _ARRL_YEAR_LINK_RE.findall(html):
                    IARU_YEAR_URLS.setdefault(
                        int(y),
                        f"https://contests.arrl.org/publiclogs.php?eid=4&iid={iid}")
            url = IARU_YEAR_URLS.get(year)
        if url is None:
            return None
        html = http_get(url)
        if not html:
            return None
        m = _ARRL_COUNT_RE.search(html)
        if m:
            return int(m.group(1).replace(",", ""))
        n = len(_ARRL_LOG_RE.findall(html))
        return n if n > 0 else None

    # cqdir 型 (cqww / cqwpx)
    html = http_get(cqdir_list_url(contest, year))
    if not html:
        return None
    n = len(set(_CQDIR_LINK_RE.findall(html)))
    return n if n > 0 else None


# ---- ローカル状態 -----------------------------------------------------------

def held_years(contest: str) -> list:
    """raw/{contest}_{year}/ に .txt が存在する年のリスト"""
    years = []
    raw_root = BASE_DIR / "raw"
    if not raw_root.is_dir():
        return years
    for d in raw_root.glob(f"{contest}_*"):
        m = re.fullmatch(rf"{re.escape(contest)}_(\d{{4}})", d.name)
        if m and any(d.glob("*.txt")):
            years.append(int(m.group(1)))
    return sorted(years)


def dir_size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def avg_log_size(contest: str) -> tuple[int, int | None]:
    """
    ローカル保持の最新年から公開ログ1件の平均サイズを実測。
    戻り値: (平均バイト数, 実測に使った年 or None)
    """
    for y in reversed(held_years(contest)):
        d = raw_log_dir(contest, y)
        files = list(d.glob("*.txt"))
        if files:
            total = sum(f.stat().st_size for f in files)
            return total // len(files), y
    return DEFAULT_AVG_LOG_BYTES, None


def json_ratio(contest: str) -> tuple[float, int | None]:
    """
    QSO系JSON（通常+approx）の合計サイズ / raw合計サイズ の実績比。
    戻り値: (比率, 実測に使った年 or None)。実績なしは既定値。
    """
    for y in reversed(held_years(contest)):
        raw = raw_log_dir(contest, y)
        if not raw.is_dir():
            continue
        raw_bytes = dir_size(raw)
        j = sum(p.stat().st_size for p in (qso_json(contest, y),
                                           qso_approx_json(contest, y))
                if p.exists())
        if raw_bytes > 0 and j > 0:
            return j / raw_bytes, y
    return 0.02, None   # 既定: rawの2%程度


def rbn_local_avg_zip() -> int | None:
    """ローカル保持の RBN zip の平均サイズ（推定フォールバック用）"""
    zips = sorted(rbn_raw_dir().glob("*.zip"))
    if not zips:
        return None
    recent = zips[-10:]
    return sum(z.stat().st_size for z in recent) // len(recent)


def rbn_json_ratio(contest: str) -> float:
    """RBN系JSON合計 / 対象期間zip合計 の実績比。実績なしは既定値。"""
    from contest_utils import rbn_raw_zips
    for y in reversed(held_years(contest)):
        zips = [p for p in rbn_raw_zips(contest, y) if p.exists()]
        if not zips:
            continue
        zip_bytes = sum(p.stat().st_size for p in zips)
        j = sum(p.stat().st_size for p in (rbn_json(contest, y),
                                           rbn_approx_json(contest, y))
                if p.exists())
        if zip_bytes > 0 and j > 0:
            return j / zip_bytes
    return 0.05   # 既定: zipの5%程度


# ---- 表示 -------------------------------------------------------------------

def fmt_bytes(n: int | None) -> str:
    if n is None:
        return "?"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f}{unit}" if unit != "B" else f"{n}B"
        n /= 1024
    return f"{n:.1f}TB"


# ---- 対象列挙・見積もり（CLI と propmap_server.py の双方から使用） ----------

def gather_targets(contests=None, all_missing=False):
    """
    公開ログサイトを確認し、取り込み対象を列挙する。
    戻り値: (targets, unpublished)
      targets:     [{"contest","year","label","logs"}]   公開済みで未保持
      unpublished: [{"contest","year","label"}]          開催済みだが未公開/確認不能
    """
    if contests is None:
        contests = list(CONTEST_CFG.keys())
    targets, unpublished = [], []
    for contest in contests:
        held = held_years(contest)
        newest_held = max(held) if held else 0
        label = CONTEST_CFG[contest]["label"]
        for year in available_years(contest):
            if year in held:
                continue
            if not all_missing and year <= newest_held:
                continue
            n = probe_public_logs(contest, year)
            if n is None:
                unpublished.append(
                    {"contest": contest, "year": year, "label": label})
            else:
                targets.append(
                    {"contest": contest, "year": year, "label": label,
                     "logs": n})
    return targets, unpublished


def build_estimate(targets):
    """
    対象リストからディスク使用量見積もりを構築する。
    戻り値: {"rows":[...], "total":int, "free":int}
      row: {"contest","year","label","logs",
            "logs_bytes","rbn_bytes"(None可),"rbn_exact","json_bytes","subtotal"}
    """
    rows = []
    total_all = 0
    avg_zip_fallback = rbn_local_avg_zip()

    for t in targets:
        contest, year, n_logs = t["contest"], t["year"], t["logs"]
        cfg = CONTEST_CFG[contest]
        avg, _sample_year = avg_log_size(contest)
        logs_bytes = n_logs * avg

        rbn_bytes = None
        exact = True
        if cfg["has_rbn"]:
            rbn_bytes = 0
            for d in get_rbn_dates(contest, year):
                dest = rbn_raw_dir() / f"{d.strftime('%Y%m%d')}.zip"
                if dest.exists():
                    rbn_bytes += dest.stat().st_size
                    continue
                sz = http_head_size(RBN_BASE_URL + d.strftime("%Y%m%d"))
                if sz is not None:
                    rbn_bytes += sz
                elif avg_zip_fallback is not None:
                    rbn_bytes += avg_zip_fallback
                    exact = False
                else:
                    rbn_bytes = None
                    break

        jr, _jr_year = json_ratio(contest)
        json_bytes = int(logs_bytes * jr)
        if cfg["has_rbn"] and rbn_bytes:
            json_bytes += int(rbn_bytes * rbn_json_ratio(contest))

        subtotal = logs_bytes + (rbn_bytes or 0) + json_bytes
        total_all += subtotal
        rows.append({"contest": contest, "year": year,
                     "label": cfg["label"], "logs": n_logs,
                     "logs_bytes": logs_bytes, "rbn_bytes": rbn_bytes,
                     "rbn_exact": exact, "json_bytes": json_bytes,
                     "subtotal": subtotal})

    usage = shutil.disk_usage(BASE_DIR if BASE_DIR.exists() else Path.home())
    return {"rows": rows, "total": total_all, "free": usage.free}


# ---- パイプライン実行 -------------------------------------------------------

def run_cmd(cmd: list, label: str) -> bool:
    print(msg(f"\n  [実行] {label}", f"\n  [RUN] {label}"))
    print(f"  >>> {' '.join(str(c) for c in cmd)}")
    rc = subprocess.call(cmd)
    if rc != 0:
        print(msg(f"  !!! エラー (rc={rc}): {label}",
                  f"  !!! Error (rc={rc}): {label}"), file=sys.stderr)
        return False
    return True


def pipeline_steps(contest: str, year: int) -> list:
    """
    generate_all.sh の run_contest と同じコマンド列を返す。
    戻り値: [(label, [cmd, ...]), ...]（cmd要素はすべて str）
    """
    py = sys.executable or "python3"
    csv_dir = BASE_DIR / "csv"
    data    = HEATMAP_DIR / "data"
    has_rbn = CONTEST_CFG[contest]["has_rbn"]

    steps = [
        (f"step1 {contest} {year}",
         [py, SCRIPT_DIR / "step1_collect_logs_fast.py",
          "--contest", contest, "--year", str(year)]),
    ]
    if has_rbn:
        steps += [
            (f"download_rbn {contest} {year}",
             [py, SCRIPT_DIR / "download_rbn.py",
              "--contest", contest, "--year", str(year)]),
            (f"make_spotted_grids {contest} {year}",
             [py, SCRIPT_DIR / "make_spotted_grids.py",
              "--contest", contest, "--year", str(year)]),
        ]
    steps += [
        (f"make_spotted_grids_approx {contest} {year}",
         [py, SCRIPT_DIR / "make_spotted_grids_approx.py",
          "--contest", contest, "--year", str(year)]),
        (f"step4_crosscheck {contest} {year}",
         [py, SCRIPT_DIR / "step4_crosscheck.py",
          "--contest", contest, "--year", str(year),
          "--max-call-dist", "2", "--band-fix-window", "15",
          "--annotate-logs"]),
        (f"step5_aggregate {contest} {year}",
         [py, SCRIPT_DIR / "step5_aggregate.py",
          "--contest", contest, "--year", str(year)]),
        (f"step4_crosscheck_approx {contest} {year}",
         [py, SCRIPT_DIR / "step4_crosscheck_approx.py",
          "--contest", contest, "--year", str(year),
          "--max-call-dist", "2", "--band-fix-window", "15",
          "--annotate-logs"]),
        (f"step5_aggregate_approx {contest} {year}",
         [py, SCRIPT_DIR / "step5_aggregate.py",
          "--contest", contest, "--year", str(year),
          "--input",  str(csv_dir / f"{contest}_{year}_qso_pairs_approx.csv"),
          "--output", str(data / f"{contest}_{year}_approx.json")]),
    ]
    if has_rbn:
        steps += [
            (f"step4_rbn {contest} {year}",
             [py, SCRIPT_DIR / "step4_rbn.py",
              "--contest", contest, "--year", str(year)]),
            (f"step5_rbn {contest} {year}",
             [py, SCRIPT_DIR / "step5_rbn.py",
              "--contest", contest, "--year", str(year)]),
            (f"step4_rbn_approx {contest} {year}",
             [py, SCRIPT_DIR / "step4_rbn_approx.py",
              "--contest", contest, "--year", str(year)]),
            (f"step5_rbn_approx {contest} {year}",
             [py, SCRIPT_DIR / "step5_rbn.py",
              "--contest", contest, "--year", str(year),
              "--input",  str(csv_dir / f"{contest}_{year}_rbn_pairs_approx.csv"),
              "--output", str(data / f"{contest}_{year}_rbn_approx.json")]),
        ]
    return [(label, [str(c) for c in cmd]) for label, cmd in steps]


def run_pipeline(contest: str, year: int) -> bool:
    """CLI用: pipeline_steps を順次実行。前段失敗時は後段を実行しない"""
    for label, cmd in pipeline_steps(contest, year):
        if not run_cmd(cmd, label):
            return False
    return True


# ---- メイン -----------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description=msg("新規開催年の公開ログ/RBNの確認と取り込み",
                        "Check and import newly published contest logs / RBN data"),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--contest", choices=list(CONTEST_CFG.keys()),
                    help=msg("対象コンテストを限定", "Limit to one contest"))
    ap.add_argument("--all-missing", action="store_true",
                    help=msg("最新年以降だけでなく過去の未保持年もすべて対象",
                             "Include all missing years, not just newer ones"))
    ap.add_argument("--dry-run", action="store_true",
                    help=msg("見積もり表示のみで終了", "Estimate only, no download"))
    ap.add_argument("--yes", action="store_true",
                    help=msg("確認プロンプトをスキップして実行",
                             "Skip confirmation prompt"))
    args = ap.parse_args()

    contests = [args.contest] if args.contest else list(CONTEST_CFG.keys())

    print(msg("公開ログサイトを確認中...", "Checking public log sites..."))
    targets, unpublished = gather_targets(contests, args.all_missing)
    for u in unpublished:
        print(msg(f"  {u['label']} {u['year']}: 未公開",
                  f"  {u['label']} {u['year']}: not published yet"))
    for t in targets:
        print(msg(f"  {t['label']} {t['year']}: 公開済み ({t['logs']:,}局)",
                  f"  {t['label']} {t['year']}: available ({t['logs']:,} logs)"))

    if not targets:
        print(msg("\n新規に取り込める公開ログはありません。",
                  "\nNo new public logs to import."))
        return

    # ---- サイズ見積もり ----
    print(msg("\n==== ディスク使用量見積もり ====",
              "\n==== Disk usage estimate ===="))
    est = build_estimate(targets)
    total_all = est["total"]

    hdr = msg(
        f"{'コンテスト':<14} {'年':<6} {'局数':>8} {'公開ログ':>10} "
        f"{'RBN zip':>10} {'JSON':>9} {'小計':>10}",
        f"{'Contest':<14} {'Year':<6} {'Logs':>8} {'Public':>10} "
        f"{'RBN zip':>10} {'JSON':>9} {'Subtotal':>10}")
    print(hdr)
    print("-" * len(hdr))
    for r in est["rows"]:
        rbn_s = fmt_bytes(r["rbn_bytes"]) if r["rbn_bytes"] is not None else "-"
        note = "" if r["rbn_exact"] else msg(" (RBN推定)", " (RBN est.)")
        print(f"{r['label']:<14} {r['year']:<6} {r['logs']:>8,} "
              f"{fmt_bytes(r['logs_bytes']):>10} "
              f"{rbn_s:>10} {fmt_bytes(r['json_bytes']):>9} "
              f"{fmt_bytes(r['subtotal']):>10}{note}")
    print("-" * len(hdr))
    print(msg(f"{'合計':<14} {'':<6} {'':<8} {'':<10} {'':<10} {'':<9} "
              f"{fmt_bytes(total_all):>10}",
              f"{'Total':<14} {'':<6} {'':<8} {'':<10} {'':<10} {'':<9} "
              f"{fmt_bytes(total_all):>10}"))
    print(msg("※ 公開ログ・JSONサイズは既存年の実績からの推定値。"
              "RBN zip は HEAD による実測（(RBN推定) 表記を除く）",
              "* Public log / JSON sizes are estimates based on held years. "
              "RBN zip sizes are measured via HEAD (unless marked est.)"))

    # ---- 空き容量チェック ----
    free = est["free"]
    print(msg(f"\n空き容量: {fmt_bytes(free)}",
              f"\nFree disk space: {fmt_bytes(free)}"))
    if free < total_all * 2:
        print(msg("警告: 空き容量が見積もりの2倍未満です"
                  "（RBNのJSON生成時の一時展開分を考慮すると不足の恐れ）",
                  "Warning: free space is less than 2x the estimate "
                  "(temporary RBN extraction during JSON generation may not fit)"))
        if free < total_all:
            print(msg("エラー: 空き容量が見積もり合計を下回っています。中断します。",
                      "Error: free space is below the estimated total. Aborting."))
            sys.exit(1)

    if args.dry_run:
        print(msg("\n[dry-run] ここで終了します。", "\n[dry-run] Stopping here."))
        return

    # ---- 確認プロンプト ----
    if not args.yes:
        try:
            ans = input(msg("\nダウンロードと取り込みを実行しますか? [y/N]: ",
                            "\nProceed with download and import? [y/N]: "))
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if ans.strip().lower() not in ("y", "yes"):
            print(msg("中止しました。", "Cancelled."))
            return

    # ---- 実行 ----
    ok_list, fail_list = [], []
    for t in targets:
        contest, year = t["contest"], t["year"]
        print(msg(f"\n======== {CONTEST_CFG[contest]['label']} {year} ========",
                  f"\n======== {CONTEST_CFG[contest]['label']} {year} ========"))
        if run_pipeline(contest, year):
            ok_list.append(f"{contest} {year}")
        else:
            fail_list.append(f"{contest} {year}")

    print(msg(f"\n完了: 成功={len(ok_list)}  失敗={len(fail_list)}",
              f"\nDone: ok={len(ok_list)}  failed={len(fail_list)}"))
    if fail_list:
        print(msg(f"  失敗: {', '.join(fail_list)}",
                  f"  Failed: {', '.join(fail_list)}"))
        sys.exit(1)


if __name__ == "__main__":
    main()
