#!/usr/bin/env python3
"""
SILSO から太陽黒点数月別データをダウンロードするスクリプト。

ダウンロード対象:
  SN_m_tot_V2.0.txt（月別平滑黒点数・1749年〜現在）
  https://www.sidc.be/SILSO/DATA/SN_m_tot_V2.0.txt

配置先: ~/heatmap/contest_logs/SN_m_tot_V2.0.txt

使い方:
  python3 fetch_ssn.py          # 最新版を取得（すでにあればレコード数を比較してスキップ）
  python3 fetch_ssn.py --force  # 強制上書き
"""
import sys
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

URL     = 'https://www.sidc.be/SILSO/DATA/SN_m_tot_V2.0.txt'
TIMEOUT = 30
OUT     = Path(__file__).parent / 'contest_logs' / 'SN_m_tot_V2.0.txt'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                  'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36',
}


def count_records(path: Path) -> int:
    try:
        return sum(1 for line in path.read_text(encoding='utf-8', errors='replace').splitlines()
                   if line.strip() and not line.startswith(';'))
    except FileNotFoundError:
        return 0


def fetch() -> bytes:
    req = Request(URL, headers=HEADERS)
    try:
        with urlopen(req, timeout=TIMEOUT) as r:
            return r.read()
    except HTTPError as e:
        raise RuntimeError(f'HTTP {e.code}: {URL}')
    except URLError as e:
        raise RuntimeError(f'URLError {e.reason}: {URL}')


def main():
    force = '--force' in sys.argv

    existing = count_records(OUT)
    if existing:
        print(msg(f'既存ファイル: {OUT}  ({existing} レコード)',
                  f'Existing file: {OUT}  ({existing} records)'))
    else:
        print(msg(f'ダウンロード先: {OUT}', f'Output: {OUT}'))

    print(msg(f'ダウンロード中: {URL}', f'Downloading: {URL}'), flush=True)
    try:
        data = fetch()
    except RuntimeError as e:
        print(msg(f'エラー: {e}', f'Error: {e}'), file=sys.stderr)
        sys.exit(1)

    new_count = sum(1 for line in data.decode('utf-8', errors='replace').splitlines()
                    if line.strip() and not line.startswith(';'))

    if not force and existing >= new_count:
        print(msg(f'最新です（{existing} レコード、変化なし）。スキップ。',
                  f'Already up-to-date ({existing} records, no change). Skipped.'))
        return

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(data)
    print(msg(f'保存完了: {OUT}  ({new_count} レコード)',
              f'Saved: {OUT}  ({new_count} records)'))
    if existing:
        diff = new_count - existing
        if diff > 0:
            print(msg(f'  {diff} レコード追加', f'  {diff} records added'))


if __name__ == '__main__':
    main()
