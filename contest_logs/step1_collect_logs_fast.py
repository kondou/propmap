#!/usr/bin/env python3
"""
step1_collect_logs_fast.py  ―  全コンテスト・全年対応 並列ダウンロード版

使い方:
  # 特定コンテスト・年を指定
  python3 step1_collect_logs_fast.py -c cqww_cw -y 2024
  python3 step1_collect_logs_fast.py -c cqww_ssb -y 2023 2024

  # コンテスト種別の全年を一括
  python3 step1_collect_logs_fast.py -c cqww_cw --all-years
  python3 step1_collect_logs_fast.py -c iaru --all-years

  # 並列数調整・テスト
  python3 step1_collect_logs_fast.py -c cqww_cw -y 2024 -w 8
  python3 step1_collect_logs_fast.py -c cqww_cw -y 2024 -n 50

利用可能なコンテスト識別子:
  iaru       IARU HF World Championship (2018-2025)
  cqww_cw    CQ WW DX CW  (2005-2025)
  cqww_ssb   CQ WW DX SSB (2005-2025)
  cqwpx_cw   CQ WPX CW    (2008-2025)
  cqwpx_ssb  CQ WPX SSB   (2008-2025)

所要時間目安 (workers=6):
  IARU    : 約4,000件 → 約12分
  CQ WW   : 約35,000件/年 → 約90-120分/年
  CQ WPX  : 約10,000件/年 → 約25-35分/年

保存先:
  ~/contest_logs/raw/{contest_key}_{year}/  ← 年ごとにディレクトリを分ける
"""

import re, time, argparse, sys
import urllib.request, urllib.error
from pathlib import Path
from html.parser import HTMLParser
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock, get_ident

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

# ---- コンテスト定義 -------------------------------------------------------

# 年リストの一次情報は contest_utils.available_years()（開催日ベースで自動導出）。
# import できない場合のみ以下の静的レンジにフォールバックする。
try:
    from contest_utils import available_years as _available_years
except ImportError:
    _available_years = None

_STATIC_YEARS = {
    "iaru":      list(range(2018, 2026)),
    "cqww_cw":   list(range(2005, 2026)),
    "cqww_ssb":  list(range(2005, 2026)),
    "cqwpx_cw":  list(range(2008, 2026)),
    "cqwpx_ssb": list(range(2008, 2026)),
}

def contest_years(contest_key: str) -> list:
    if _available_years is not None:
        try:
            return _available_years(contest_key)
        except Exception:
            pass
    return _STATIC_YEARS[contest_key]

# 既知の IARU 年別URL（キャッシュ）。未知の年は resolve_iaru_iid() が
# 既知ページの「Public logs are available for these years:」リンクから自動解決する。
IARU_YEAR_URLS = {
    2018: "https://contests.arrl.org/publiclogs.php?eid=4&iid=202",
    2019: "https://contests.arrl.org/publiclogs.php?eid=4&iid=683",
    2020: "https://contests.arrl.org/publiclogs.php?eid=4&iid=714",
    2021: "https://contests.arrl.org/publiclogs.php?eid=4&iid=997",
    2022: "https://contests.arrl.org/publiclogs.php?eid=4&iid=1022",
    2023: "https://contests.arrl.org/publiclogs.php?eid=4&iid=1053",
    2024: "https://contests.arrl.org/publiclogs.php?eid=4&iid=1064",
    2025: "https://contests.arrl.org/publiclogs.php?eid=4&iid=1110",
}

# 年ページ内リンク: <a href="publiclogs.php?eid=4&iid=NNN">YYYY</a>
_IARU_YEAR_LINK_RE = re.compile(
    r'href="(?:https?://contests\.arrl\.org/)?publiclogs\.php\?eid=4&(?:amp;)?iid=(\d+)"[^>]*>\s*(\d{4})\s*<',
    re.IGNORECASE)

_iaru_resolved = False

def resolve_iaru_iid(year: int) -> str | None:
    """
    IARU の年別URLを返す。IARU_YEAR_URLS になければ、既知の最新ページを
    1回取得して年→iidリンク一覧をスクレイプし、IARU_YEAR_URLS を更新する。
    """
    global _iaru_resolved
    if year in IARU_YEAR_URLS:
        return IARU_YEAR_URLS[year]
    if _iaru_resolved:
        return None
    _iaru_resolved = True

    seed_url = IARU_YEAR_URLS[max(IARU_YEAR_URLS)]
    html = fetch(seed_url)
    if not html:
        return None
    found = 0
    for iid, y in _IARU_YEAR_LINK_RE.findall(html):
        y = int(y)
        if y not in IARU_YEAR_URLS:
            IARU_YEAR_URLS[y] = \
                f"https://contests.arrl.org/publiclogs.php?eid=4&iid={iid}"
            found += 1
    if found:
        print(msg(f"  IARU 年別URLを自動解決: {found}件追加",
                  f"  IARU year URLs auto-resolved: {found} added"))
    return IARU_YEAR_URLS.get(year)

SSN_TABLE = {
    "iaru":      {2018:45,2019:68,2020:20,2021:30,2022:95,2023:145,2024:180,2025:160},
    "cqww_cw":   {2005:30,2006:15,2007:10,2008:5,2009:3,2010:18,2011:55,2012:90,
                  2013:115,2014:110,2015:80,2016:55,2017:35,2018:25,2019:5,
                  2020:10,2021:40,2022:105,2023:160,2024:190,2025:170},
    "cqww_ssb":  {2005:30,2006:20,2007:12,2008:5,2009:3,2010:15,2011:45,2012:80,
                  2013:110,2014:105,2015:75,2016:50,2017:30,2018:20,2019:8,
                  2020:8,2021:35,2022:98,2023:155,2024:185,2025:165},
    "cqwpx_cw":  {2008:8,2009:5,2010:12,2011:40,2012:75,2013:100,2014:98,
                  2015:70,2016:45,2017:28,2018:22,2019:12,2020:12,2021:25,
                  2022:90,2023:148,2024:178,2025:155},
    "cqwpx_ssb": {2008:8,2009:5,2010:10,2011:30,2012:65,2013:88,2014:92,
                  2015:65,2016:40,2017:25,2018:18,2019:10,2020:10,2021:22,
                  2022:80,2023:140,2024:170,2025:148},
}

CONTEST_DEFS = {
    "iaru": {
        "years": lambda: contest_years("iaru"),
        "get_list_url": lambda y: resolve_iaru_iid(y),
        "base_url": "https://contests.arrl.org",
        "log_type": "arrl",
    },
    "cqww_cw": {
        "years": lambda: contest_years("cqww_cw"),
        "get_list_url": lambda y: f"https://cqww.com/publiclogs/{y}cw/",
        "base_url": "https://cqww.com",
        "log_type": "cqdir",
    },
    "cqww_ssb": {
        "years": lambda: contest_years("cqww_ssb"),
        "get_list_url": lambda y: f"https://cqww.com/publiclogs/{y}ph/",
        "base_url": "https://cqww.com",
        "log_type": "cqdir",
    },
    "cqwpx_cw": {
        "years": lambda: contest_years("cqwpx_cw"),
        "get_list_url": lambda y: f"https://cqwpx.com/publiclogs/{y}cw/",
        "base_url": "https://cqwpx.com",
        "log_type": "cqdir",
    },
    "cqwpx_ssb": {
        "years": lambda: contest_years("cqwpx_ssb"),
        "get_list_url": lambda y: f"https://cqwpx.com/publiclogs/{y}ph/",
        "base_url": "https://cqwpx.com",
        "log_type": "cqdir",
    },
}

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"}
BASE_SAVE = Path(__file__).resolve().parent / "raw"

# ---- HTMLパーサー ----------------------------------------------------------

class LogListParser(HTMLParser):
    def __init__(self, base_url, log_type, list_url=""):
        super().__init__()
        self.base_url = base_url
        self.log_type = log_type
        if list_url and not list_url.endswith("/"):
            list_url = list_url.rsplit("/", 1)[0] + "/"
        self.list_dir = list_url
        self.urls = []

    def handle_starttag(self, tag, attrs):
        if tag != "a": return
        href = dict(attrs).get("href","")
        if not href: return

        if self.log_type == "arrl":
            if "showpubliclog.php" in href:
                url = href if href.startswith("http") \
                      else self.base_url + "/" + href.lstrip("/")
                self.urls.append(url)

        elif self.log_type == "cqdir":
            low = href.lower()
            if any(low.endswith(ext) for ext in (".log",".cbr",".txt")):
                if href.startswith("http"):
                    url = href
                elif href.startswith("/"):
                    url = self.base_url + href
                else:
                    url = self.list_dir + href.lstrip("/")
                self.urls.append(url)

# ---- ネットワーク ----------------------------------------------------------

def fetch(url: str, retries: int = 3, timeout: int = 25) -> str | None:
    req = urllib.request.Request(url, headers=HEADERS)
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
                for enc in ("utf-8","latin-1","cp1252"):
                    try: return raw.decode(enc)
                    except: pass
                return raw.decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            if e.code in (403,404): return None
            time.sleep(min(2**attempt, 8))
        except Exception:
            time.sleep(min(2**attempt, 8))
    return None

def safe_filename(call: str) -> str:
    return re.sub(r"[^\w\-]", "_", call)

def extract_callsign(text: str) -> str | None:
    m = re.search(r"^CALLSIGN:\s*(\S+)", text, re.MULTILINE|re.IGNORECASE)
    return m.group(1).upper() if m else None

# ---- ワーカー --------------------------------------------------------------
_lock = Lock()
_cnt  = {"done":0,"skip":0,"fail":0}

def expected_path_from_url(url: str, save_dir: Path, log_type: str) -> Path | None:
    """
    URLから保存先ファイル名を推定する（フェッチ前スキップ用）。
    cqdir型はURL末尾がほぼコールサイン（例: ja1abc.log → JA1ABC.txt）。
    CALLSIGNヘッダと不一致の稀なケースは推定パスが存在せず再取得されるだけで安全。
    arrl型はURLにコールサインを含まないため推定不可（Noneを返す）。
    """
    if log_type != "cqdir":
        return None
    stem = url.rstrip("/").rsplit("/", 1)[-1]
    stem = re.sub(r"\.(log|cbr|txt)$", "", stem, flags=re.IGNORECASE)
    if not stem:
        return None
    return save_dir / f"{safe_filename(stem.upper())}.txt"

def download_one(url: str, save_dir: Path, resume: bool,
                 log_type: str = "cqdir") -> str:
    # フェッチ前スキップ: URL由来のファイル名が既存ならダウンロード自体を省略
    if resume:
        exp = expected_path_from_url(url, save_dir, log_type)
        if exp is not None and exp.exists():
            with _lock: _cnt["skip"] += 1
            return "skip"

    content = fetch(url)
    if not content:
        with _lock: _cnt["fail"] += 1
        return "fail"

    call = extract_callsign(content)
    if not call:
        with _lock: _cnt["fail"] += 1
        return "fail"

    path = save_dir / f"{safe_filename(call)}.txt"
    if resume and path.exists():
        with _lock: _cnt["skip"] += 1
        return "skip"

    # 中断時に不完全なファイルを「完了」として残さないよう、一時ファイルに
    # 書いてから rename する
    tmp = path.with_suffix(path.suffix + f".part{get_ident()}")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)
    with _lock: _cnt["done"] += 1
    return "new"

# ---- 1年分収集 -------------------------------------------------------------

def collect_year(contest_key: str, year: int, workers: int,
                 max_logs: int | None, resume: bool) -> int:
    defn = CONTEST_DEFS[contest_key]
    list_url = defn["get_list_url"](year)
    if not list_url:
        print(msg(f"  [{contest_key}/{year}] URL未定義",
                  f"  [{contest_key}/{year}] URL not defined"))
        return 0

    save_dir = BASE_SAVE / f"{contest_key}_{year}"
    save_dir.mkdir(parents=True, exist_ok=True)

    html = fetch(list_url)
    if not html:
        print(msg(f"  [{contest_key}/{year}] 一覧取得失敗: {list_url}",
                  f"  [{contest_key}/{year}] Failed to fetch list: {list_url}"))
        return 0

    parser = LogListParser(defn["base_url"], defn["log_type"], list_url)
    parser.feed(html)
    urls = parser.urls

    if not urls:
        print(msg(f"  [{contest_key}/{year}] ログURL 0件 → {list_url}",
                  f"  [{contest_key}/{year}] No log URLs found → {list_url}"))
        return 0

    if max_logs:
        urls = urls[:max_logs]

    total = len(urls)
    print(msg(f"\n[{contest_key} / {year}]  {total} 件  → {save_dir}",
              f"\n[{contest_key} / {year}]  {total} logs  → {save_dir}"))

    with _lock:
        _cnt["done"] = _cnt["skip"] = _cnt["fail"] = 0

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(download_one, u, save_dir, resume,
                             defn["log_type"]): u for u in urls}
        for i, fut in enumerate(as_completed(futures), 1):
            fut.result()
            if i % 500 == 0 or i == total:
                elapsed = time.time()-t0
                rate = i/elapsed if elapsed > 0 else 0
                remain = (total-i)/rate if rate > 0 else 0
                with _lock:
                    print(msg(
                        f"  {i:5d}/{total}  "
                        f"new={_cnt['done']} skip={_cnt['skip']} fail={_cnt['fail']}  "
                        f"{rate:.1f}件/s  残り約{remain/60:.1f}分",
                        f"  {i:5d}/{total}  "
                        f"new={_cnt['done']} skip={_cnt['skip']} fail={_cnt['fail']}  "
                        f"{rate:.1f} logs/s  ETA~{remain/60:.1f}min",
                    ))

    with _lock:
        elapsed = time.time()-t0
        print(msg(
            f"  完了 {elapsed/60:.1f}分  "
            f"new={_cnt['done']} skip={_cnt['skip']} fail={_cnt['fail']}",
            f"  Done {elapsed/60:.1f}min  "
            f"new={_cnt['done']} skip={_cnt['skip']} fail={_cnt['fail']}",
        ))
        return _cnt["done"]

# ---- メイン ----------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Contest log downloader")
    ap.add_argument("-c","--contest", required=True,
                    choices=list(CONTEST_DEFS.keys()))
    ap.add_argument("-y","--years", type=int, nargs="+",
                    help=msg("対象年（複数可）", "Target year(s)"))
    ap.add_argument("--all-years", action="store_true",
                    help=msg("コンテストの全年を対象", "Process all available years"))
    ap.add_argument("-w","--workers", type=int, default=6)
    ap.add_argument("-n","--max-logs", type=int, default=None,
                    help=msg("最大件数（テスト用）", "Max logs to fetch (for testing)"))
    ap.add_argument("--no-resume", dest="resume",
                    action="store_false", default=True)
    args = ap.parse_args()

    defn = CONTEST_DEFS[args.contest]

    valid_years = defn["years"]()
    if args.all_years:
        years = valid_years
    elif args.years:
        bad = [y for y in args.years if y not in valid_years]
        if bad:
            print(msg(f"対応外の年: {bad}  対応年: {valid_years}",
                      f"Unsupported year(s): {bad}  Valid: {valid_years}"))
            return
        years = args.years
    else:
        ap.error(msg("-y/--years か --all-years を指定してください",
                     "Specify -y/--years or --all-years"))
        return

    print(msg(f"コンテスト: {args.contest}", f"Contest:  {args.contest}"))
    print(msg(f"対象年    : {years}",         f"Years:    {years}"))
    print(msg(f"並列数    : {args.workers}",  f"Workers:  {args.workers}"))
    print(msg(f"resume    : {args.resume}",   f"Resume:   {args.resume}"))
    print(msg(f"保存先    : {BASE_SAVE}",     f"Save dir: {BASE_SAVE}"))

    total_new = 0
    for year in sorted(years):
        total_new += collect_year(
            args.contest, year, args.workers, args.max_logs, args.resume)

    print(msg(f"\n全体完了: 新規取得 {total_new} 件",
              f"\nAll done: {total_new} new logs downloaded"))

if __name__ == "__main__":
    main()
