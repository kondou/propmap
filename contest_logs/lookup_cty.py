#!/usr/bin/env python3
"""
cty.dat群からコールサイン→グリッドロケータを引くモジュール。

使い方（モジュールとして）:
    from lookup_cty import CtyLookup
    cty = CtyLookup()
    grid, src = cty.lookup('JA1ABC')      # -> ('PM95', 'area')
    grid, src = cty.lookup('3B8/SM6GOR')  # -> ('LG89', 'entity')
    grid, src = cty.lookup('W3ABC/7')     # -> ('DN31', 'area')
    grid, src = cty.lookup('JA1FFO/MM')   # -> (None, 'no-locator')

使い方（単体実行）:
    python3 lookup_cty.py JA1ABC 3B8/SM6GOR W3ABC/7
    python3 lookup_cty.py --debug JA1ABC

grid_source 戻り値:
    'exact'      : cty.dat に完全一致エントリ (=CALLSIGN) があった
    'area'       : /数字 サフィックスによるコールエリア変更
    'entity'     : /X 形式でエンティティプリフィックス側が判定できた
    'stripped'   : /P /QRP /M を除去して一致
    'prefix'     : 通常の最長プリフィックスマッチ
    'no-locator' : /MM または /AM（運用場所不定）
    'ambiguous'  : どちらがエンティティか判定不能（個別定義が必要）
    'not-found'  : cty.dat に一致なし
"""

import re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# ---- i18n -------------------------------------------------------------------
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
        return 'en'
    _L = _dlang()
    def msg(ja, en=''): return ja if _L == 'ja' else (en or ja)
# -----------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# グリッド計算
# ---------------------------------------------------------------------------
def latlon_to_grid4(lat, lon_east):
    """緯度経度（lon = positive East）から4文字グリッドロケータを返す。"""
    lon_adj = lon_east + 180
    lat_adj = lat + 90
    if not (0 <= lon_adj < 360) or not (0 <= lat_adj < 180):
        return None
    field = chr(65 + int(lon_adj / 20)) + chr(65 + int(lat_adj / 10))
    sq    = str(int((lon_adj % 20) / 2)) + str(int(lat_adj % 10))
    return field + sq


# ---------------------------------------------------------------------------
# パース補助
# ---------------------------------------------------------------------------
# エンティティヘッダー行のパターン
_HDR_RE = re.compile(
    r'^([^:]+):\s*(\d+):\s*(\d+):\s*([A-Z]{2}):\s*(-?\d+\.?\d*):'
    r'\s*(-?\d+\.?\d*):\s*(-?\d+\.?\d*):\s*([A-Z0-9\/\-]+):\s*$'
)
# プリフィックス内のモディファイア（CQゾーン等）を除去
_MOD_RE = re.compile(r'\([^)]*\)|\[[^\]]*\]|<[^>]*>|~[^~]*~')


# ---------------------------------------------------------------------------
# メインクラス
# ---------------------------------------------------------------------------
class CtyLookup:
    def __init__(self, cty_dir=None, verbose=True):
        """
        cty_dir: cty.dat等が置かれたディレクトリ。省略時は cty_data/cty-最新/ を自動検出。
        """
        if cty_dir is None:
            # contest_logs/ の親が heatmap/、その下に cty_data/
            base = Path(__file__).parent.parent / 'cty_data'
            dirs = sorted(
                (d for d in base.glob('cty-[0-9]*') if d.is_dir()),
                key=lambda p: int(p.name.split('-')[1])
            )
            if not dirs:
                raise FileNotFoundError(
                    msg(f'cty_data/ が見つかりません: {base}',
                        f'cty_data/ not found: {base}'))
            cty_dir = dirs[-1]
        self.cty_dir = Path(cty_dir)
        self._prefix_map = {}   # prefix_upper → (lat, lon_east, label)
        self._exact_map  = {}   # callsign_upper → (lat, lon_east, label)
        self._verbose    = verbose
        self._load()

    # ---- 読み込み ----------------------------------------------------------

    def _load(self):
        # 読み込み順: cty.dat（エンティティ基本）→ 各 *_cty.dat（詳細サブエンティティ）
        # 後から読んだファイルで上書き → サブエンティティが優先される
        files = []
        cty_main = self.cty_dir / 'cty.dat'
        if cty_main.exists():
            files.append(cty_main)
        # 大文字で始まるか cty_rus.dat など _cty.dat で終わる全ファイル
        for f in sorted(self.cty_dir.iterdir()):
            if f.name == 'cty.dat':
                continue
            if f.suffix == '.dat' and ('_cty' in f.name or f.name[0].isupper()):
                files.append(f)

        for path in files:
            self._parse_file(path)

        if self._verbose:
            print(msg(
                f'cty.dat 読み込み完了: {len(self._prefix_map)} プリフィックス, '
                f'{len(self._exact_map)} 完全一致  [{self.cty_dir.name}]',
                f'cty.dat loaded: {len(self._prefix_map)} prefixes, '
                f'{len(self._exact_map)} exact  [{self.cty_dir.name}]'
            ), file=sys.stderr)

    def _parse_file(self, path):
        try:
            text = path.read_text(encoding='utf-8', errors='replace')
        except OSError:
            return

        current_lat = current_lon = current_label = None
        in_entity   = False
        prefix_buf  = ''

        for raw_line in text.splitlines():
            line = raw_line.rstrip()
            if not line or line.startswith('#'):
                continue

            m = _HDR_RE.match(line)
            if m:
                if in_entity and prefix_buf:
                    self._register_prefixes(prefix_buf, current_lat, current_lon, current_label)
                    prefix_buf = ''
                # cty.dat longitude: positive West → negate for positive East
                current_lat   = float(m.group(5))
                current_lon   = -float(m.group(6))
                current_label = m.group(8).strip()
                in_entity     = True
                continue

            if in_entity:
                prefix_buf += ' ' + line
                if ';' in line:
                    self._register_prefixes(prefix_buf, current_lat, current_lon, current_label)
                    prefix_buf  = ''
                    in_entity   = False

        if in_entity and prefix_buf:
            self._register_prefixes(prefix_buf, current_lat, current_lon, current_label)

    def _register_prefixes(self, buf, lat, lon_east, label):
        raw = buf.replace(';', ' ').replace(',', ' ')
        for token in raw.split():
            token = token.strip()
            if not token:
                continue
            clean = _MOD_RE.sub('', token).strip()
            if not clean:
                continue
            if clean.startswith('='):
                call = clean[1:].upper()
                if call:
                    self._exact_map[call] = (lat, lon_east, label)
            else:
                prefix = clean.upper()
                if prefix:
                    self._prefix_map[prefix] = (lat, lon_east, label)

    # ---- コールサイン正規化 ------------------------------------------------

    def _normalize(self, callsign):
        """
        コールサインを正規化して (lookup_str, source_hint) を返す。
        lookup_str が None なら 'no-locator'。
        source_hint: 'direct' / 'stripped' / 'area' / 'entity' / 'ambiguous' / 'no-locator'
        """
        cs = callsign.upper().strip()

        if '/' not in cs:
            return cs, 'direct'

        # 複数の / があるケース（例: 3B8/SM6GOR/P）→ 末尾から処理
        parts = cs.rsplit('/', 1)
        left, right = parts[0], parts[1]

        # /MM, /AM → ロケータなし
        if right in ('MM', 'AM'):
            return None, 'no-locator'

        # /P, /QRP, /M → サフィックス除去して再帰
        if right in ('P', 'QRP', 'M'):
            return self._normalize(left)

        # /単数字 → コールエリア変更
        if len(right) == 1 and right.isdigit():
            # 左側コールサインの文字部分（先頭の英字連続）+ 新数字
            m = re.match(r'^([A-Z]+)', left)
            if m:
                candidate = m.group(1) + right
                # candidateがcty.datに存在すればそのまま使用
                if candidate in self._prefix_map:
                    return candidate, 'area'
                # 存在しなければ left のエンティティ内のエリアとしてフォールバック
            return left, 'stripped'

        # entity/call or call/entity の判定
        entity = self._determine_entity(left, right)
        if entity is None:
            return cs, 'ambiguous'
        return entity, 'entity'

    def _determine_entity(self, left, right):
        """2パーツのどちらがエンティティプリフィックスかを判定して返す。不明はNone。"""
        def ends_digit(s):  return bool(s) and s[-1].isdigit()
        def has_digit(s):   return any(c.isdigit() for c in s)

        le, re_ = ends_digit(left), ends_digit(right)
        lh, rh  = has_digit(left),  has_digit(right)

        # 数字で終わる方がエンティティプリフィックス
        if le and not re_: return left
        if re_ and not le: return right

        # どちらも数字で終わらない
        if not le and not re_:
            if not lh and rh:  return left   # 英字のみ → エンティティ
            if not rh and lh:  return right
            # cty.dat に存在する方
            l_in = left  in self._prefix_map
            r_in = right in self._prefix_map
            if l_in and not r_in: return left
            if r_in and not l_in: return right

        return None  # 判定不能

    # ---- 公開 API ----------------------------------------------------------

    def lookup(self, callsign):
        """
        コールサインからグリッドロケータを返す。
        戻り値: (grid4_str or None, source_str)
        """
        lookup_str, hint = self._normalize(callsign)

        if lookup_str is None:
            return None, hint  # 'no-locator'

        if hint == 'ambiguous':
            return None, 'ambiguous'

        cs = lookup_str.upper()

        # 完全一致チェック（=CONTESTエントリ等）
        if cs in self._exact_map:
            lat, lon, _ = self._exact_map[cs]
            g = latlon_to_grid4(lat, lon)
            return g, 'exact'

        # 最長プリフィックスマッチ
        for length in range(len(cs), 0, -1):
            prefix = cs[:length]
            if prefix in self._prefix_map:
                lat, lon, _ = self._prefix_map[prefix]
                g = latlon_to_grid4(lat, lon)
                src = hint if hint in ('area', 'entity', 'stripped') else 'prefix'
                return g, src

        return None, 'not-found'

    def lookup_batch(self, callsigns):
        """
        複数コールサインをまとめて引く。
        戻り値: {callsign: (grid4 or None, source_str)}
        """
        return {cs: self.lookup(cs) for cs in callsigns}


# ---------------------------------------------------------------------------
# 単体実行
# ---------------------------------------------------------------------------
def main():
    import argparse
    ap = argparse.ArgumentParser(
        description=msg('cty.datからコールサインのグリッドを引く',
                        'Look up callsign grids from cty.dat'))
    ap.add_argument('callsigns', nargs='*',
                    help=msg('コールサイン（複数可）', 'callsign(s)'))
    ap.add_argument('--debug', action='store_true',
                    help=msg('内部状態を詳細表示', 'show debug info'))
    ap.add_argument('--cty-dir', default=None,
                    help=msg('cty.datディレクトリ', 'cty.dat directory'))
    args = ap.parse_args()

    if not args.callsigns:
        print(msg('使い方: python3 lookup_cty.py [--debug] コールサイン [...]',
                  'Usage: python3 lookup_cty.py [--debug] callsign [...]'))
        sys.exit(1)

    cty = CtyLookup(cty_dir=args.cty_dir)

    if args.debug:
        print(msg(f'\nプリフィックス総数: {len(cty._prefix_map)}',
                  f'\nTotal prefixes: {len(cty._prefix_map)}'))
        print(msg(f'完全一致総数: {len(cty._exact_map)}\n',
                  f'Total exact: {len(cty._exact_map)}\n'))

    print(msg(f'{"コールサイン":<16}  {"グリッド":<8}  {"ソース":<12}',
              f'{"Callsign":<16}  {"Grid":<8}  {"Source":<12}'))
    print('-' * 40)
    for cs in args.callsigns:
        grid, src = cty.lookup(cs)
        print(f'{cs:<16}  {grid or "-":<8}  {src}')


if __name__ == '__main__':
    main()
