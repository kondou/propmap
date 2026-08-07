#!/usr/bin/env python3
"""
fetch_rbn_nodes.py
RBN ノードリスト (rbn_nodes.csv) を構築・更新する。

取得戦略:
  1. RBN サイト (detail_json.php) から現行アクティブノードを取得
  2. rbn/raw/*.zip をスキャンして過去コンテストで使われた全スポッターを収集
  3. サイトに載っていない旧ノードは cty.dat でグリッドを補完

使い方:
  python3 fetch_rbn_nodes.py          # 差分更新（新規ノードのみ補完）
  python3 fetch_rbn_nodes.py --force  # 全ノードを再取得
  python3 fetch_rbn_nodes.py --dry-run

出力: ~/heatmap/contest_logs/rbn/rbn_nodes.csv  (callsign,grid)
"""

import sys, csv, json, re, io, zipfile
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

SCRIPT_DIR   = Path(__file__).parent
CONTEST_LOGS = SCRIPT_DIR / 'contest_logs'
RBN_DIR      = CONTEST_LOGS / 'rbn'
RAW_DIR      = RBN_DIR / 'raw'
OUT_CSV      = RBN_DIR / 'rbn_nodes.csv'

sys.path.insert(0, str(CONTEST_LOGS))

# ---- i18n -------------------------------------------------------------------
import locale as _lc, os as _os
def _dlang():
    for v in [_os.environ.get(e, '') for e in ('LANG', 'LC_ALL', 'LANGUAGE')]:
        if v: return 'ja' if v.lower().startswith('ja') else 'en'
    if sys.platform == 'win32':
        # 「地域の形式」ではなくOSの表示言語(UI言語)で判定する
        try:
            import ctypes
            lid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            return 'ja' if (lid & 0x3FF) == 0x11 else 'en'
        except Exception:
            return 'en'
    try:
        _lc.setlocale(_lc.LC_ALL, '')
        lc = _lc.getlocale()[0] or ''
        if lc.lower().startswith('ja'): return 'ja'
    except Exception: pass
    return 'en'
_L = _dlang()
def msg(ja, en=''): return ja if _L == 'ja' else (en or ja)
# -----------------------------------------------------------------------------

RBN_JSON_URL = 'https://www.reversebeacon.net/nodes/detail_json.php'
TIMEOUT      = 30
HEADERS      = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                  'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36',
    'Referer': 'https://www.reversebeacon.net/nodes/detail.php',
}

_CALL_RE = re.compile(r'^[A-Z0-9][A-Z0-9/\-]{1,}$', re.IGNORECASE)

try:
    from lookup_cty import CtyLookup
    _HAS_CTY = True
except ImportError:
    _HAS_CTY = False


def fetch_rbn_site() -> dict:
    """RBN サイトから現行ノード {callsign: grid4} を取得する。"""
    req = Request(RBN_JSON_URL, headers=HEADERS)
    try:
        with urlopen(req, timeout=TIMEOUT) as r:
            data = json.loads(r.read().decode('utf-8', errors='replace'))
    except (HTTPError, URLError) as e:
        print(msg(f'  警告: RBN サイト取得失敗: {e}',
                  f'  Warning: RBN site fetch failed: {e}'), file=sys.stderr)
        return {}
    nodes = {}
    for entry in data:
        call = str(entry.get('call', '')).strip().upper()
        grid = str(entry.get('grid', '')).strip().upper()[:4]
        if call and grid:
            nodes[call] = grid
    return nodes


def collect_spotters_from_raw() -> set:
    """rbn/raw/*.zip から全スポッターコールサインを収集する。"""
    calls = set()
    for zp in sorted(RAW_DIR.glob('*.zip')):
        try:
            with zipfile.ZipFile(zp) as z:
                for name in z.namelist():
                    if not name.endswith('.csv'):
                        continue
                    data = z.read(name).decode('utf-8', errors='replace')
                    for row in csv.DictReader(io.StringIO(data)):
                        c = row.get('callsign', '').strip().upper()
                        if c and _CALL_RE.match(c):
                            calls.add(c)
        except Exception as e:
            print(msg(f'  警告: {zp.name} 読み込みエラー: {e}',
                      f'  Warning: error reading {zp.name}: {e}'), file=sys.stderr)
    return calls


def load_existing() -> dict:
    """既存の rbn_nodes.csv を {callsign: grid} で返す。"""
    nodes = {}
    if not OUT_CSV.exists():
        return nodes
    with open(OUT_CSV, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            c = row.get('callsign', '').strip().upper()
            g = row.get('grid', '').strip().upper()
            if c:
                nodes[c] = g
    return nodes


def main():
    force   = '--force'   in sys.argv
    dry_run = '--dry-run' in sys.argv

    if dry_run:
        print(msg('[dry-run: 変更を保存しません]', '[dry-run: changes will not be saved]'))
    if force:
        print(msg('[--force: 全ノードを再取得]', '[--force: re-fetching all nodes]'))

    # 1. RBN サイトから現行ノード取得
    print(msg('RBN サイトから現行ノード取得中...', 'Fetching current nodes from RBN site...'),
          flush=True)
    site_nodes = fetch_rbn_site()
    print(msg(f'  {len(site_nodes)} ノード取得', f'  {len(site_nodes)} nodes fetched'))

    # 2. raw zip から過去スポッター収集
    raw_spotters = set()
    if RAW_DIR.exists():
        print(msg(f'raw zip スキャン: {RAW_DIR}', f'Scanning raw zips: {RAW_DIR}'))
        raw_spotters = collect_spotters_from_raw()
        print(msg(f'  {len(raw_spotters)} スポッター収集',
                  f'  {len(raw_spotters)} spotters collected'))

    # 3. 既存 CSV 読み込み
    existing = load_existing()
    print(msg(f'既存 CSV: {len(existing)} エントリ',
              f'Existing CSV: {len(existing)} entries'))

    # サイト情報を優先してマージ
    merged = dict(existing)
    for call, grid in site_nodes.items():
        if force or call not in merged or not merged[call]:
            merged[call] = grid

    # サイトに載っていない旧ノードのうち補完が必要なもの
    unknown = sorted(
        c for c in raw_spotters
        if force or c not in merged or not merged.get(c)
    )
    print(msg(f'cty.dat で補完: {len(unknown)} コールサイン',
              f'Resolving via cty.dat: {len(unknown)} callsigns'))

    # 4. cty.dat で補完
    if unknown:
        cty = None
        if _HAS_CTY:
            try:
                cty = CtyLookup(verbose=False)
            except Exception as e:
                print(msg(f'  警告: cty.dat 初期化失敗 ({e})',
                          f'  Warning: cty.dat init failed ({e})'), file=sys.stderr)

        found = 0; not_found = 0
        for call in unknown:
            grid = None
            if cty is not None:
                try:
                    grid, _ = cty.lookup(call)
                except Exception:
                    pass
            merged[call] = grid[:4] if grid else merged.get(call, '')
            if grid:
                found += 1
            else:
                not_found += 1

        print(msg(f'  取得: {found}  未解決: {not_found}',
                  f'  Resolved: {found}  not found: {not_found}'))

    # 5. 書き出し
    new_count = len(merged)
    if not dry_run:
        OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
        with open(OUT_CSV, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['callsign', 'grid'])
            for call in sorted(merged.keys()):
                w.writerow([call, merged[call]])
        print(msg(f'保存: {OUT_CSV}  ({new_count} エントリ)',
                  f'Saved: {OUT_CSV}  ({new_count} entries)'))
        diff = new_count - len(existing)
        if diff > 0:
            print(msg(f'  {diff} エントリ追加', f'  {diff} entries added'))
        elif diff < 0:
            print(msg(f'  {-diff} エントリ減少', f'  {-diff} entries removed'))
    else:
        print(msg(f'合計 {new_count} エントリ（保存なし）',
                  f'Total {new_count} entries (not saved)'))


if __name__ == '__main__':
    main()
