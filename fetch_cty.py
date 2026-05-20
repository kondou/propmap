#!/usr/bin/env python3
"""
country-files.com から最新の cty.dat 一式をダウンロードするスクリプト。

ダウンロード対象:
  - 標準CTY zip (cty-NNNN.zip) から必要ファイルのみ展開:
      cty.dat, AF_cty.dat, AS_cty.dat, BY_cty.dat, EU_cty.dat,
      NA_cty.dat, SA_cty.dat, VK_cty.dat, cty_rus.dat
  - BigCTY zip (bigcty-YYYYMMDD.zip) から cty.dat のみ展開

展開先: cty_data/cty-{VERSION}/  および cty_data/bigcty-{YYYYMMDD}/

使い方:
  python3 fetch_cty.py          # 最新版を取得（すでにあればスキップ）
  python3 fetch_cty.py --force  # 強制再取得
"""
import io, re, sys, zipfile
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

# ---- i18n -------------------------------------------------------------------
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

BASE_URL  = 'https://www.country-files.com'
TIMEOUT   = 30
OUT_DIR   = Path(__file__).parent / 'cty_data'

CTY_FILES_NEEDED = {
    'cty.dat', 'AF_cty.dat', 'AS_cty.dat', 'BY_cty.dat',
    'EU_cty.dat', 'NA_cty.dat', 'SA_cty.dat', 'VK_cty.dat', 'cty_rus.dat',
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                  'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36',
    'Referer': BASE_URL + '/',
}


def fetch(url):
    req = Request(url, headers=HEADERS)
    try:
        with urlopen(req, timeout=TIMEOUT) as r:
            return r.read()
    except HTTPError as e:
        raise RuntimeError(f'HTTP {e.code}: {url}')
    except URLError as e:
        raise RuntimeError(f'URLError {e.reason}: {url}')


def find_latest_links(html: str):
    cty_m = re.search(
        r'href="(https://www\.country-files\.com/cty/download/(\d+)/cty-\d+\.zip)"',
        html)
    bigcty_m = re.search(
        r'href="(https://www\.country-files\.com/bigcty/download/\d+/bigcty-(\d{8})\.zip)"',
        html)
    return (
        cty_m.group(2) if cty_m else None,
        cty_m.group(1) if cty_m else None,
        bigcty_m.group(2) if bigcty_m else None,
        bigcty_m.group(1) if bigcty_m else None,
    )


def download_and_extract(zip_url: str, dest_dir: Path, files_needed: set | None):
    print(msg(f'  ダウンロード中: {zip_url}', f'  Downloading: {zip_url}'), flush=True)
    data = fetch(zip_url)
    print(msg(f'  展開中 → {dest_dir}', f'  Extracting → {dest_dir}'), flush=True)
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            parts = Path(info.filename).parts
            if 'old' in parts:
                continue
            name = parts[-1]
            if files_needed is not None and name not in files_needed:
                continue
            target = dest_dir / name
            target.write_bytes(z.read(info.filename))
            print(f'    {name} ({info.file_size:,} bytes)')


def main():
    force = '--force' in sys.argv

    print(msg('トップページ取得中...', 'Fetching index page...'), flush=True)
    html = fetch(BASE_URL + '/').decode('utf-8', errors='replace')

    cty_ver, cty_url, bigcty_date, bigcty_url = find_latest_links(html)

    if not cty_url:
        print(msg('エラー: CTY ダウンロードURLが見つからない',
                  'Error: CTY download URL not found'), file=sys.stderr)
        sys.exit(1)

    print(msg(f'最新CTY    : {cty_ver}  ({cty_url})',
              f'Latest CTY    : {cty_ver}  ({cty_url})'))
    if bigcty_url:
        print(msg(f'最新BigCTY : {bigcty_date}  ({bigcty_url})',
                  f'Latest BigCTY : {bigcty_date}  ({bigcty_url})'))

    # 標準CTY
    cty_dir = OUT_DIR / f'cty-{cty_ver}'
    if cty_dir.exists() and not force:
        print(msg(f'\n標準CTY はすでに取得済み: {cty_dir}',
                  f'\nStandard CTY already downloaded: {cty_dir}'))
    else:
        print(msg('\n標準CTY を取得します...', '\nDownloading standard CTY...'))
        if cty_dir.exists():
            import shutil; shutil.rmtree(cty_dir)
        download_and_extract(cty_url, cty_dir, CTY_FILES_NEEDED)

    # BigCTY
    if bigcty_url:
        bigcty_dir = OUT_DIR / f'bigcty-{bigcty_date}'
        if bigcty_dir.exists() and not force:
            print(msg(f'\nBigCTY はすでに取得済み: {bigcty_dir}',
                      f'\nBigCTY already downloaded: {bigcty_dir}'))
        else:
            print(msg('\nBigCTY を取得します...', '\nDownloading BigCTY...'))
            if bigcty_dir.exists():
                import shutil; shutil.rmtree(bigcty_dir)
            download_and_extract(bigcty_url, bigcty_dir, {'cty.dat'})

    print(msg('\n完了。', '\nDone.'))
    print(msg(f'取得先: {OUT_DIR}', f'Output: {OUT_DIR}'))


if __name__ == '__main__':
    main()
