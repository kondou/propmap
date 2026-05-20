#!/usr/bin/env python3
"""
QRZ.comからグリッドロケータを取得するスクリプト。

使い方:
  # トライアル: 任意のコールサインを指定
  python3 fetch_qrz.py JA1ABC JA2XYZ W1AW ...

  # トライアル: --debug でページ解析の詳細を表示
  python3 fetch_qrz.py --debug JA1ABC JA2XYZ

  # コールサインリストをファイルから一括取得（SQLiteキャッシュ使用）
  python3 fetch_qrz.py --bulk no_locator_calls.txt

  # キャッシュ統計表示
  python3 fetch_qrz.py --cache-stats
"""
import re, sys, time, sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

RATE      = 2.0   # リクエスト間隔（秒）= 0.5件/秒
TIMEOUT   = 15    # タイムアウト（秒）
CACHE_DB  = Path(__file__).parent / 'qrz_cache.db'

GRID_RE = re.compile(r'^[A-R]{2}[0-9]{2}([A-X]{2})?$', re.IGNORECASE)

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/124.0.0.0 Safari/537.36'
    ),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}


def latlon_to_grid4(lat, lon):
    """緯度経度から4文字グリッドロケータを計算する。"""
    lon_adj = lon + 180
    lat_adj = lat + 90
    field = chr(ord('A') + int(lon_adj / 20)) + chr(ord('A') + int(lat_adj / 10))
    sq    = str(int((lon_adj % 20) / 2)) + str(int(lat_adj % 10))
    return field + sq


# ---------------------------------------------------------------------------
# SQLiteキャッシュ
# ---------------------------------------------------------------------------

def open_cache():
    conn = sqlite3.connect(CACHE_DB)
    conn.execute('''CREATE TABLE IF NOT EXISTS qrz (
        callsign TEXT PRIMARY KEY,
        grid     TEXT,
        method   TEXT,
        fetched  TEXT
    )''')
    conn.commit()
    return conn

def cache_get(conn, callsign):
    """キャッシュ済みなら (grid, method)、未登録はNone。"""
    return conn.execute(
        'SELECT grid, method FROM qrz WHERE callsign=?', (callsign.upper(),)
    ).fetchone()

def cache_put(conn, callsign, grid, method):
    conn.execute(
        'INSERT OR REPLACE INTO qrz (callsign, grid, method, fetched) VALUES (?,?,?,?)',
        (callsign.upper(), grid, method,
         datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'))
    )
    conn.commit()

def show_cache_stats():
    if not CACHE_DB.exists():
        print('キャッシュなし')
        return
    conn = open_cache()
    total   = conn.execute('SELECT COUNT(*) FROM qrz').fetchone()[0]
    found   = conn.execute("SELECT COUNT(*) FROM qrz WHERE grid IS NOT NULL").fetchone()[0]
    no_rec  = conn.execute("SELECT COUNT(*) FROM qrz WHERE method='no-record'").fetchone()[0]
    no_grid = conn.execute("SELECT COUNT(*) FROM qrz WHERE method='not-found'").fetchone()[0]
    conn.close()
    print(f'キャッシュ: {CACHE_DB}')
    print(f'  総数          : {total}')
    print(f'  グリッド取得済: {found}')
    print(f'  QRZ未登録     : {no_rec}')
    print(f'  登録あり・グリッドなし: {no_grid}')


# ---------------------------------------------------------------------------
# フェッチ
# ---------------------------------------------------------------------------

def fetch_html(callsign):
    """QRZ.comのページHTMLを返す。戻り値: (html, final_url, error_msg)。"""
    url = f'https://www.qrz.com/db/{callsign.upper()}'
    req = Request(url, headers=HEADERS)
    try:
        with urlopen(req, timeout=TIMEOUT) as resp:
            final_url = resp.url
            return resp.read().decode('utf-8', errors='replace'), final_url, None
    except HTTPError as e:
        return None, None, f'HTTP {e.code}'
    except URLError as e:
        return None, None, f'URLError: {e.reason}'
    except Exception as e:
        return None, None, str(e)


# ---------------------------------------------------------------------------
# グリッド抽出
# ---------------------------------------------------------------------------

_TAG_RE = re.compile(r'<[^>]+>')

def _strip_tags(s):
    return _TAG_RE.sub(' ', s)


def extract_grid(html, callsign='', final_url='', debug=False):
    """HTMLからグリッドロケータを抽出。
    戻り値: (raw_str|None, method_str)
    """
    # 0. not-found 判定: タイトルがコールサインで始まらない
    title_m = re.search(r'<title>([^<]*)</title>', html, re.IGNORECASE)
    title = title_m.group(1).strip() if title_m else ''
    if debug:
        print(f'  [D0] title={title!r}')
    if callsign and not title.upper().startswith(callsign.upper()):
        return None, 'no-record'

    # 1. JS変数 cs_lat / cs_lon からグリッドを計算（QRZの主要パターン）
    lat_m = re.search(r'var\s+cs_lat\s*=\s*"(-?\d+\.?\d*)"', html)
    lon_m = re.search(r'var\s+cs_lon\s*=\s*"(-?\d+\.?\d*)"', html)
    if debug:
        print(f'  [D1] cs_lat={lat_m and lat_m.group(1)!r}, cs_lon={lon_m and lon_m.group(1)!r}')
    if lat_m and lon_m:
        try:
            lat = float(lat_m.group(1))
            lon = float(lon_m.group(1))
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                return latlon_to_grid4(lat, lon), 'latlon-js'
        except ValueError:
            pass

    # 2. "Grid Square" ラベル後300文字（タグ除去）からグリッド値を探す（フォールバック）
    for m in re.finditer(r'Grid\s*(?:Square|Locator|Sq\.?)?', html, re.IGNORECASE):
        window = html[m.end(): m.end() + 300]
        text = _strip_tags(window)
        if debug:
            print(f'  [D2] Grid@{m.start()}: {repr(text[:80])}')
        for gm in re.finditer(r'\b([A-R]{2}[0-9]{2}(?:[A-X]{2})?)\b', text, re.IGNORECASE):
            val = gm.group(1).upper()
            if GRID_RE.match(val):
                if debug:
                    print(f'  [D2] → hit: {val}')
                return val, 'grid-label'

    return None, 'not-found'


# ---------------------------------------------------------------------------
# バルク取得
# ---------------------------------------------------------------------------

def _fmt_eta(seconds):
    if seconds < 60:
        return f'{seconds:.0f}s'
    if seconds < 3600:
        return f'{seconds/60:.0f}m'
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    return f'{h}h{m:02d}m'

def run_bulk(call_file):
    path = Path(call_file)
    if not path.exists():
        print(f'ファイルが見つからない: {call_file}', file=sys.stderr)
        sys.exit(1)

    calls = [ln.strip().upper() for ln in path.read_text().splitlines()
             if ln.strip() and not ln.startswith('#')]
    total = len(calls)
    print(f'対象: {total} 局  キャッシュ: {CACHE_DB}', file=sys.stderr)

    conn = open_cache()
    stats = {'found': 0, 'no_record': 0, 'not_found': 0, 'error': 0, 'cached': 0}
    t_start = time.time()
    fetch_n = 0  # 実際にHTTPリクエストした数

    for i, call in enumerate(calls):
        # キャッシュヒット
        cached = cache_get(conn, call)
        if cached is not None:
            grid, method = cached
            stats['cached'] += 1
            if method == 'no-record':
                stats['no_record'] += 1
            elif grid:
                stats['found'] += 1
            else:
                stats['not_found'] += 1
            _progress(i + 1, total, call, t_start, fetch_n, suffix='[cache]')
            continue

        # レート制限
        if fetch_n > 0:
            time.sleep(RATE)
        fetch_n += 1

        html, final_url, err = fetch_html(call)
        if err:
            stats['error'] += 1
            print(f'\n[{i+1}/{total}] {call:<12}  —         error           {err}')
            _progress(i + 1, total, call, t_start, fetch_n)
            continue

        grid, method = extract_grid(html, callsign=call, final_url=final_url)
        cache_put(conn, call, grid, method)

        if method == 'no-record':
            stats['no_record'] += 1
        elif grid:
            stats['found'] += 1
            print(f'\n[{i+1}/{total}] {call:<12}  {grid:<8}  {method}')
        else:
            stats['not_found'] += 1

        _progress(i + 1, total, call, t_start, fetch_n)

    conn.close()
    elapsed = time.time() - t_start
    print(f'\n\n=== 完了 ({elapsed/3600:.1f}h) ===', file=sys.stderr)
    print(f'  グリッド取得    : {stats["found"]}')
    print(f'  QRZ未登録       : {stats["no_record"]}')
    print(f'  登録あり・グリッドなし: {stats["not_found"]}')
    print(f'  エラー          : {stats["error"]}')
    print(f'  キャッシュ済スキップ: {stats["cached"]}')

def _progress(i, total, call, t_start, fetch_n, suffix=''):
    elapsed = time.time() - t_start
    pct = i / total * 100
    if fetch_n > 0 and elapsed > 0:
        eta = _fmt_eta((total - i) * elapsed / fetch_n) if fetch_n < i else \
              _fmt_eta((total - i) * RATE)
    else:
        eta = '?'
    line = f'  [{i}/{total} {pct:.1f}%] {call:<12} 残り≈{eta} {suffix}   '
    print(line, end='\r', file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------

def main():
    args        = sys.argv[1:]
    debug       = '--debug'       in args
    save_html   = '--save-html'   in args
    cache_stats = '--cache-stats' in args
    bulk_idx    = next((i for i, a in enumerate(args) if a == '--bulk'), None)

    if cache_stats:
        show_cache_stats()
        return

    if bulk_idx is not None:
        if bulk_idx + 1 >= len(args):
            print('使い方: --bulk <コールサインリストファイル>', file=sys.stderr)
            sys.exit(1)
        run_bulk(args[bulk_idx + 1])
        return

    calls = [a for a in args if not a.startswith('--')]
    if not calls:
        print('使い方: python3 fetch_qrz.py [--debug] [--save-html] コールサイン [...]')
        print('        python3 fetch_qrz.py --bulk <ファイル>')
        print('        python3 fetch_qrz.py --cache-stats')
        sys.exit(1)

    print(f'{"コールサイン":<12}  {"グリッド":<8}  {"取得方法":<16}  備考')
    print('-' * 60)

    for i, call in enumerate(calls):
        if i > 0:
            time.sleep(RATE)

        html, final_url, err = fetch_html(call)
        if err:
            print(f'{call:<12}  {"—":<8}  {"error":<16}  {err}')
            continue

        if save_html:
            fname = f'{call.upper()}_dump.html'
            Path(fname).write_text(html, encoding='utf-8')
            print(f'  [saved] {fname}')

        grid, method = extract_grid(html, callsign=call, final_url=final_url, debug=debug)
        note = '' if grid else '(登録なし or 抽出失敗)'
        print(f'{call:<12}  {(grid or "—"):<8}  {method:<16}  {note}')


if __name__ == '__main__':
    main()
