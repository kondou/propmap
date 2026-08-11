#!/usr/bin/env python3
"""
cty.dat群からコールサイン→グリッドロケータを引くモジュール。

使い方（モジュールとして）:
    from lookup_cty import CtyLookup
    cty = CtyLookup()
    grid, src = cty.lookup('JA1ABC')      # -> ('PM95', 'area')
    grid, src = cty.lookup('3B8/SM6GOR')  # -> ('LG89', 'entity')
    grid, src = cty.lookup('W3ABC/7')     # -> ('DN11', 'area')
    grid, src = cty.lookup('JA1FFO/MM')   # -> (None, 'no-locator')

    # エンティティ名・大陸コードも要るとき（EU/非EU判定など）
    info = cty.lookup_info('IT9GSF')
    # -> CtyInfo(grid='JM77', source='prefix', entity='Sicily',
    #            continent='EU', prefix='*IT9')

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
from collections import namedtuple
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
# 末尾のプライマリプリフィックス欄は '*' 始まり（WAEリスト固有エンティティ）と
# 小文字（*GM/s, *JW/b）を取り得る。ここを弾くとそのエンティティのブロックごと
# 読み飛ばされるので、文字クラスを狭めないこと。
_HDR_RE = re.compile(
    r'^([^:]+):\s*(\d+):\s*(\d+):\s*([A-Z]{2}):\s*(-?\d+\.?\d*):'
    r'\s*(-?\d+\.?\d*):\s*(-?\d+\.?\d*):\s*([*A-Za-z0-9\/\-]+):\s*$'
)
# プリフィックス内のモディファイア（CQゾーン等）を除去
_MOD_RE = re.compile(r'\([^)]*\)|\[[^\]]*\]|<[^>]*>|~[^~]*~')

# cty.dat のエンティティ1件分。src は読み込み元ファイル名（衝突解決に使う）
_Ent = namedtuple('_Ent', 'lat lon entity continent prefix src')

# lookup_info() の戻り値。見つからなかった場合 grid 以外も None になる
CtyInfo = namedtuple('CtyInfo', 'grid source entity continent prefix')


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
        self._prefix_map = {}   # prefix_upper   → _Ent
        self._exact_map  = {}   # callsign_upper → _Ent
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

        current_ent = None
        in_entity   = False
        prefix_buf  = ''

        for raw_line in text.splitlines():
            line = raw_line.rstrip()
            if not line or line.startswith('#'):
                continue

            m = _HDR_RE.match(line)
            if m:
                if in_entity and prefix_buf:
                    self._register_prefixes(prefix_buf, current_ent)
                    prefix_buf = ''
                # cty.dat longitude: positive West → negate for positive East
                current_ent = _Ent(lat=float(m.group(5)),
                                   lon=-float(m.group(6)),
                                   entity=m.group(1).strip(),
                                   continent=m.group(4).strip().upper(),
                                   prefix=m.group(8).strip(),
                                   src=path.name)
                in_entity   = True
                continue

            if in_entity:
                prefix_buf += ' ' + line
                if ';' in line:
                    self._register_prefixes(prefix_buf, current_ent)
                    prefix_buf  = ''
                    in_entity   = False

        if in_entity and prefix_buf:
            self._register_prefixes(prefix_buf, current_ent)

    def _register_prefixes(self, buf, ent):
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
                    # 別ファイル間の上書きは _load() の設計どおり後勝ち
                    # （サブエンティティファイルが基本エンティティを上書きする）。
                    # 同一ファイル内で衝突した場合だけ、'*' 付き（WAEリスト固有の
                    # サブエンティティ）を優先する。cty.dat 内の記載順は
                    # 特異性を表さないため、後勝ちだと Vienna Intl Ctr が
                    # Austria に潰される等、広い方が勝ってしまう。
                    prev = self._exact_map.get(call)
                    if (prev is not None and prev.src == ent.src
                            and prev.prefix.startswith('*')
                            and not ent.prefix.startswith('*')):
                        continue
                    self._exact_map[call] = ent
            else:
                prefix = clean.upper()
                if prefix:
                    self._prefix_map[prefix] = ent

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

    def lookup_info(self, callsign):
        """
        コールサインからグリッド＋エンティティ情報を返す。
        戻り値: CtyInfo(grid, source, entity, continent, prefix)
                引けなかった場合は grid 以外も None。

        continent は cty.dat の大陸コード（'EU' 'AS' 'NA' 'SA' 'AF' 'OC' 'AN'）。
        prefix はプライマリプリフィックスで、WAEリスト固有のエンティティ
        （Sicily 等）は '*' で始まる。
        """
        raw = callsign.upper().strip()

        # 生のコールサインでの完全一致を最優先で見る。
        # cty.dat の完全一致エントリには '=SV2ASP/A' のようにスラッシュを含む
        # ものが165件あり、_normalize() を通すと別トークンに分解されてしまって
        # 到達できない（例: SV2ASP/A → 'A' を引きに行って not-found）。
        # ただし /MM /AM は運用場所が定まらないため、cty.dat に個別エントリが
        # あってもロケータを与えない方針を維持する。
        if (raw in self._exact_map
                and not raw.endswith('/MM') and not raw.endswith('/AM')):
            e = self._exact_map[raw]
            return CtyInfo(latlon_to_grid4(e.lat, e.lon), 'exact',
                           e.entity, e.continent, e.prefix)

        lookup_str, hint = self._normalize(callsign)

        if lookup_str is None:
            return CtyInfo(None, hint, None, None, None)  # 'no-locator'

        if hint == 'ambiguous':
            return CtyInfo(None, 'ambiguous', None, None, None)

        cs = lookup_str.upper()

        # 完全一致チェック（=CONTESTエントリ等）
        if cs in self._exact_map:
            e = self._exact_map[cs]
            return CtyInfo(latlon_to_grid4(e.lat, e.lon), 'exact',
                           e.entity, e.continent, e.prefix)

        # 最長プリフィックスマッチ
        for length in range(len(cs), 0, -1):
            prefix = cs[:length]
            if prefix in self._prefix_map:
                e = self._prefix_map[prefix]
                src = hint if hint in ('area', 'entity', 'stripped') else 'prefix'
                return CtyInfo(latlon_to_grid4(e.lat, e.lon), src,
                               e.entity, e.continent, e.prefix)

        return CtyInfo(None, 'not-found', None, None, None)

    def lookup(self, callsign):
        """
        コールサインからグリッドロケータを返す。
        戻り値: (grid4_str or None, source_str)
        """
        info = self.lookup_info(callsign)
        return info.grid, info.source

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

    print(msg(f'{"コールサイン":<16}  {"グリッド":<8}  {"ソース":<12}  '
              f'{"大陸":<4}  {"エンティティ"}',
              f'{"Callsign":<16}  {"Grid":<8}  {"Source":<12}  '
              f'{"Cont":<4}  {"Entity"}'))
    print('-' * 72)
    for cs in args.callsigns:
        i = cty.lookup_info(cs)
        print(f'{cs:<16}  {i.grid or "-":<8}  {i.source:<12}  '
              f'{i.continent or "-":<4}  {i.entity or "-"}')


if __name__ == '__main__':
    main()
