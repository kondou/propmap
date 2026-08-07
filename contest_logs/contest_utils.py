"""
contest_utils.py: コンテスト共通ユーティリティ

コンテスト識別子と年からパス・日程を自動解決する。
各stepスクリプトからimportして使用する。
"""
import locale, os, sys
from datetime import date, timedelta, datetime
from pathlib import Path

# ---- i18n ----------------------------------------------------------------
def _detect_lang():
    """Detect display language: env vars first, then the OS UI language."""
    for ev in ('LANG', 'LC_ALL', 'LANGUAGE', 'LC_MESSAGES'):
        v = os.environ.get(ev, '')
        if v:
            return 'ja' if v.lower().startswith('ja') else 'en'
    if sys.platform == 'win32':
        # 「地域の形式」（locale/レジストリ）ではなくOSの表示言語(UI言語)で
        # 判定する。表示言語=英語・地域=日本のような構成で誤判定しないため。
        try:
            import ctypes
            lid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            return 'ja' if (lid & 0x3FF) == 0x11 else 'en'
        except Exception:
            return 'en'
    try:
        locale.setlocale(locale.LC_ALL, '')
        lc = locale.getlocale()[0] or ''
        if lc.lower().startswith('ja'):
            return 'ja'
    except Exception:
        pass
    return 'en'

_LANG = _detect_lang()

def msg(ja, en=''):
    """Return ja or en string depending on detected language.
    Falls back to ja when en is empty."""
    return ja if _LANG == 'ja' else (en or ja)

# ---- コンテスト定義 -------------------------------------------------------
# first_year: 公開ログが利用可能な最初の年。
#             最終年はハードコードせず available_years() が現在日から導出する。
CONTEST_CFG = {
    "iaru": {
        "label":      "IARU HF",
        "mode":       "MIXED",   # CW+SSB
        "start_hour": 12,
        "hours":      24,
        "schedule":   "second_full_weekend",
        "month":      7,
        "has_rbn":    True,
        "first_year": 2018,
    },
    "cqww_cw": {
        "label":      "CQ WW CW",
        "mode":       "CW",
        "start_hour": 0,
        "hours":      48,
        "schedule":   "last_full_weekend",
        "month":      11,
        "has_rbn":    True,
        "first_year": 2005,
    },
    "cqww_ssb": {
        "label":      "CQ WW SSB",
        "mode":       "SSB",
        "start_hour": 0,
        "hours":      48,
        "schedule":   "last_full_weekend",
        "month":      10,
        "has_rbn":    False,
        "first_year": 2005,
    },
    "cqwpx_cw": {
        "label":      "CQ WPX CW",
        "mode":       "CW",
        "start_hour": 0,
        "hours":      48,
        "schedule":   "last_full_weekend",
        "month":      5,
        "has_rbn":    True,
        "first_year": 2008,
    },
    "cqwpx_ssb": {
        "label":      "CQ WPX SSB",
        "mode":       "SSB",
        "start_hour": 0,
        "hours":      48,
        "schedule":   "last_full_weekend",
        "month":      3,
        "has_rbn":    False,
        "first_year": 2008,
    },
}

# contest_utils.py は ~/heatmap/contest_logs/ に置かれる前提で、自分自身の
# 位置からパスを解決する（フォルダ名が "heatmap" である必要はない）
BASE_DIR      = Path(__file__).resolve().parent
HEATMAP_DIR   = BASE_DIR.parent

# ---- 日程計算 -------------------------------------------------------------
def second_full_weekend(year: int, month: int) -> date:
    """その月の第2 full weekendの土曜日を返す"""
    d = date(year, month, 1)
    days_to_sat = (5 - d.weekday()) % 7
    first_sat = d + timedelta(days=days_to_sat)
    return first_sat + timedelta(7)

def last_full_weekend(year: int, month: int) -> date:
    """その月の最終 full weekendの土曜日を返す"""
    if month == 12:
        last_day = date(year + 1, 1, 1) - timedelta(1)
    else:
        last_day = date(year, month + 1, 1) - timedelta(1)
    days_back = (last_day.weekday() - 5) % 7
    last_sat = last_day - timedelta(days_back)
    # 翌日曜が同月内でなければ1週前へ
    if (last_sat + timedelta(1)).month != month:
        last_sat -= timedelta(7)
    return last_sat

def get_contest_dates(contest: str, year: int):
    """
    コンテストの開始・終了datetimeを返す (UTC)
    戻り値: (start_dt, end_dt)
    """
    cfg = CONTEST_CFG[contest]
    month = cfg["month"]
    if cfg["schedule"] == "second_full_weekend":
        sat = second_full_weekend(year, month)
    else:
        sat = last_full_weekend(year, month)
    start = datetime(sat.year, sat.month, sat.day, cfg["start_hour"], 0)
    end   = start + timedelta(hours=cfg["hours"]) - timedelta(seconds=1)
    return start, end

def available_years(contest: str, today: date = None) -> list:
    """
    そのコンテストで開催済みの年リストを返す (first_year〜)。
    最終年はハードコードせず、開催日が today 以前であるかで判定する。
    （公開ログが実際に存在するかはサイト側の確認が必要。
      check_new_logs.py がリモート確認を行う）
    """
    cfg = CONTEST_CFG[contest]
    if today is None:
        today = date.today()
    years = []
    y = cfg["first_year"]
    while True:
        start, _ = get_contest_dates(contest, y)
        if start.date() > today:
            break
        years.append(y)
        y += 1
    return years


def get_rbn_dates(contest: str, year: int):
    """RBN raw dataの対象日リストを返す (date objects)"""
    start, end = get_contest_dates(contest, year)
    days = []
    d = start.date()
    while d <= end.date():
        days.append(d)
        d += timedelta(1)
    return days

# ---- パス解決 -------------------------------------------------------------
def contest_year_id(contest: str, year: int) -> str:
    return f"{contest}_{year}"

def raw_log_dir(contest: str, year: int) -> Path:
    return BASE_DIR / "raw" / contest_year_id(contest, year)

def spotted_grids_csv(contest: str, year: int) -> Path:
    return BASE_DIR / "rbn" / f"{contest_year_id(contest, year)}_spotted_grids.csv"

def rbn_raw_dir() -> Path:
    return BASE_DIR / "rbn" / "raw"

def rbn_raw_zips(contest: str, year: int) -> list:
    """コンテスト期間のRBN raw zipファイルパスリストを返す（存在するもののみ）"""
    rdir = rbn_raw_dir()
    paths = []
    for d in get_rbn_dates(contest, year):
        p = rdir / f"{d.strftime('%Y%m%d')}.zip"
        paths.append(p)
    return paths

def qso_pairs_csv(contest: str, year: int) -> Path:
    return BASE_DIR / "csv" / f"{contest_year_id(contest, year)}_qso_pairs.csv"

def rbn_pairs_csv(contest: str, year: int) -> Path:
    return BASE_DIR / "csv" / f"{contest_year_id(contest, year)}_rbn_pairs.csv"

def spotted_grids_approx_csv(contest: str, year: int) -> Path:
    return BASE_DIR / "rbn" / f"{contest_year_id(contest, year)}_spotted_grids_approx.csv"

def qso_pairs_approx_csv(contest: str, year: int) -> Path:
    return BASE_DIR / "csv" / f"{contest_year_id(contest, year)}_qso_pairs_approx.csv"

def rbn_pairs_approx_csv(contest: str, year: int) -> Path:
    return BASE_DIR / "csv" / f"{contest_year_id(contest, year)}_rbn_pairs_approx.csv"

def qso_approx_json(contest: str, year: int) -> Path:
    return HEATMAP_DIR / "data" / f"{contest}_{year}_approx.json"

def rbn_approx_json(contest: str, year: int) -> Path:
    return HEATMAP_DIR / "data" / f"{contest}_{year}_rbn_approx.json"

def qso_json(contest: str, year: int) -> Path:
    return HEATMAP_DIR / "data" / f"{contest}_{year}.json"

def rbn_json(contest: str, year: int) -> Path:
    return HEATMAP_DIR / "data" / f"{contest}_{year}_rbn.json"

def validate_contest(contest: str):
    if contest not in CONTEST_CFG:
        raise ValueError(msg(
            f"不明なコンテスト: {contest}\n有効: {list(CONTEST_CFG.keys())}",
            f"Unknown contest: {contest}\nValid: {list(CONTEST_CFG.keys())}",
        ))

# ---- SSN 自動解決 ---------------------------------------------------------
# SILSOファイルの探索候補（スクリプト配置ディレクトリは呼び出し側で先頭追加）
_SILSO_CANDIDATES = [
    BASE_DIR / "rbn" / "SN_m_tot_V2.0.txt",
    BASE_DIR / "SN_m_tot_V2.0.txt",
]

def load_ssn_table(extra_dirs=None):
    """
    SN_m_tot_V2.0.txt を読み込み {(year, month): ssn} を返す。
    extra_dirs: 追加探索ディレクトリのリスト（スクリプト配置ディレクトリ等）
    ファイルが見つからない場合は None を返す。
    """
    candidates = []
    if extra_dirs:
        for d in extra_dirs:
            candidates.append(Path(d) / "SN_m_tot_V2.0.txt")
    candidates.extend(_SILSO_CANDIDATES)

    for path in candidates:
        if not path.exists():
            continue
        table = {}
        try:
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                parts = line.split()
                if len(parts) < 4:
                    continue
                try:
                    y, m, ssn = int(parts[0]), int(parts[1]), float(parts[3])
                    if ssn >= 0:   # -1 は未確定値
                        table[(y, m)] = round(ssn)
                except ValueError:
                    continue
        except OSError:
            continue
        if table:
            print(msg(
                f"SSNデータ読み込み: {path} ({len(table)} 件)",
                f"SSN data loaded: {path} ({len(table)} entries)",
            ))
            return table
    return None

def resolve_ssn(contest: str, year: int, ssn_override=None, script_dir=None):
    """
    SSNを解決して返す。優先順位:
      1. ssn_override が None でなければそれを使用（--ssn 手動指定）
      2. SILSOファイルからコンテスト開催月のSSNを取得
      3. 取得できなければ 0 を返し警告を表示

    script_dir: 呼び出しスクリプトのディレクトリ（Path(__file__).parent を渡す）
    """
    if ssn_override is not None:
        return ssn_override

    cfg = CONTEST_CFG.get(contest, {})
    contest_month = cfg.get("month")
    if contest_month is None:
        print(msg(
            f"警告: コンテスト '{contest}' の開催月が不明。SSN=0 を使用します。",
            f"Warning: contest month unknown for '{contest}'. Using SSN=0.",
        ))
        return 0

    extra = [script_dir] if script_dir else None
    table = load_ssn_table(extra_dirs=extra)
    if table is None:
        print(msg(
            "警告: SILSOファイルが見つかりません。SSN=0 を使用します。",
            "Warning: SILSO file not found. Using SSN=0.",
        ))
        print(msg(
            f"  配置場所の候補: {_SILSO_CANDIDATES[0]}",
            f"  Expected location: {_SILSO_CANDIDATES[0]}",
        ))
        print("  Download: https://www.sidc.be/SILSO/DATA/SN_m_tot_V2.0.txt")
        return 0

    ssn = table.get((year, contest_month))
    if ssn is None:
        print(msg(
            f"警告: {year}年{contest_month}月のSSNがファイルに見つかりません。SSN=0 を使用します。",
            f"Warning: SSN for {year}/{contest_month:02d} not found in file. Using SSN=0.",
        ))
        return 0

    print(msg(
        f"SSN自動解決: {year}年{contest_month}月 = {ssn}",
        f"SSN resolved: {year}/{contest_month:02d} = {ssn}",
    ))
    return ssn


# ---- CLI: generate_all.sh / .bat 用のコンテスト×年リスト出力 ----------------
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(
        description=msg("コンテスト×年の一覧を出力（generate_all 用）",
                        "List contest/year tuples (for generate_all)"))
    ap.add_argument("--list", action="store_true",
                    help=msg("'contest year has_rbn' を1行ずつ出力",
                             "Print 'contest year has_rbn' per line"))
    args = ap.parse_args()
    if args.list:
        for _c, _cfg in CONTEST_CFG.items():
            for _y in available_years(_c):
                print(f"{_c} {_y} {1 if _cfg['has_rbn'] else 0}")
