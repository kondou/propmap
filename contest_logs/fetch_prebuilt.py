#!/usr/bin/env python3
"""
fetch_prebuilt.py - 構築済みヒートマップJSONのダウンロード（CLI兼サーバー用ライブラリ）

GitHub Releases のローリングリリース（タグ data-latest）に置かれた
manifest.json と構築済み data/*.json を取得し、ローカル data/ に配置する。
自前構築（check_new_logs.py）の代わりに数分でデータを揃えられる。

使い方:
  python3 fetch_prebuilt.py --list      # 配布状況とローカル保持状況の一覧
  python3 fetch_prebuilt.py --dry-run   # ダウンロード対象と合計サイズのみ表示
  python3 fetch_prebuilt.py             # 未保持分をダウンロード（確認あり）
  python3 fetch_prebuilt.py --yes       # 確認なしで実行

配布元の変更: 環境変数 PROPMAP_DATA_URL にベースURLを指定
  （既定: https://github.com/kondou/propmap/releases/download/data-latest）

manifest.json 形式:
  {"generated": "...", "files": [{"name","size","sha256"}, ...]}
"""

import hashlib
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

SCRIPT_DIR = Path(__file__).resolve().parent
HEATMAP_DIR = SCRIPT_DIR.parent
DATA_DIR = HEATMAP_DIR / "data"

sys.path.insert(0, str(SCRIPT_DIR))
from contest_utils import CONTEST_CFG, msg   # noqa: E402

DEFAULT_BASE_URL = ("https://github.com/kondou/propmap"
                    "/releases/download/data-latest")
TIMEOUT = 60
CHUNK = 1 << 16

# {contest}_{year}[ _approx | _rbn | _rbn_approx ].json
_FILE_RE = re.compile(r"^([a-z_]+?)_(\d{4})(_approx|_rbn|_rbn_approx)?\.json$")


def base_url() -> str:
    return os.environ.get("PROPMAP_DATA_URL", DEFAULT_BASE_URL).rstrip("/")


def _get(url: str, no_cache: bool = False) -> bytes:
    headers = {"User-Agent": "PropMap-fetch-prebuilt"}
    if no_cache:
        headers["Cache-Control"] = "no-cache"
        headers["Pragma"] = "no-cache"
    req = Request(url, headers=headers)
    with urlopen(req, timeout=TIMEOUT) as r:
        return r.read()


def fetch_manifest() -> dict:
    """配布 manifest を取得して返す。失敗時は例外。"""
    url = base_url() + "/manifest.json"
    # 配信側のキャッシュが古い manifest を返すことがある。データ更新の直後に
    # 取得しても新しい年が出てこない、という形で表面化するため、URLを毎回
    # 変えて確実に迂回する。データ本体はファイル名が年ごとに固有で、かつ
    # sha256 で検証するのでこの処理は不要。
    if url.startswith(("http://", "https://")):
        url += ("&" if "?" in url else "?") + f"t={int(time.time())}"
    data = _get(url, no_cache=True)
    m = json.loads(data.decode("utf-8"))
    if not isinstance(m.get("files"), list):
        raise ValueError("invalid manifest: no files list")
    return m


def gather_prebuilt(manifest: dict) -> list:
    """
    manifest とローカル data/ を突き合わせ、コンテスト×年単位の行を返す。
    行: {"contest","year","label","files":[{"name","size","sha256","need"}],
         "need_bytes","held"}
    need = ローカルに無い、またはサイズ不一致。held = 全ファイル取得済み。
    """
    groups = {}
    for f in manifest["files"]:
        name = f.get("name", "")
        m = _FILE_RE.match(name)
        if not m or m.group(1) not in CONTEST_CFG:
            continue
        key = (m.group(1), int(m.group(2)))
        local = DATA_DIR / name
        need = (not local.is_file()) or local.stat().st_size != f["size"]
        groups.setdefault(key, []).append(
            {"name": name, "size": f["size"],
             "sha256": f.get("sha256"), "need": need})

    rows = []
    for (contest, year), files in sorted(groups.items()):
        need_bytes = sum(f["size"] for f in files if f["need"])
        rows.append({
            "contest": contest, "year": year,
            "label": CONTEST_CFG[contest]["label"],
            "files": sorted(files, key=lambda f: f["name"]),
            "need_bytes": need_bytes,
            "held": need_bytes == 0,
        })
    return rows


def build_estimate_prebuilt(rows: list) -> dict:
    """選択行のダウンロード見積もり。{"rows","total","free"}"""
    total = sum(r["need_bytes"] for r in rows)
    free = shutil.disk_usage(HEATMAP_DIR).free
    return {"rows": rows, "total": total, "free": free}


def download_file(entry: dict, progress_cb=None) -> None:
    """
    manifest エントリ1件を data/ にダウンロードする。
    .part に書いてから sha256 検証（manifest に有る場合）→ rename。
    progress_cb(done_bytes, total_bytes) を随時呼ぶ。失敗時は例外。
    """
    name, size = entry["name"], entry["size"]
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    part = DATA_DIR / (name + ".part")
    url = base_url() + "/" + name
    h = hashlib.sha256()
    done = 0
    req = Request(url, headers={"User-Agent": "PropMap-fetch-prebuilt"})
    with urlopen(req, timeout=TIMEOUT) as r, open(part, "wb") as w:
        while True:
            chunk = r.read(CHUNK)
            if not chunk:
                break
            w.write(chunk)
            h.update(chunk)
            done += len(chunk)
            if progress_cb:
                progress_cb(done, size)
    if done != size:
        part.unlink(missing_ok=True)
        raise IOError(f"{name}: size mismatch ({done} != {size})")
    if entry.get("sha256") and h.hexdigest() != entry["sha256"]:
        part.unlink(missing_ok=True)
        raise IOError(f"{name}: sha256 mismatch")
    part.replace(DATA_DIR / name)


def fmt_bytes(n) -> str:
    if n is None:
        return "-"
    units = ["B", "KB", "MB", "GB", "TB"]
    x = float(n)
    for u in units:
        if x < 1024 or u == units[-1]:
            return (f"{x:.1f}{u}" if u != "B" else f"{int(x)}{u}")
        x /= 1024


def main():
    list_only = "--list" in sys.argv
    dry_run = "--dry-run" in sys.argv
    yes = "--yes" in sys.argv

    print(msg(f"配布元: {base_url()}", f"Source: {base_url()}"))
    print(msg("manifest 取得中...", "Fetching manifest..."), flush=True)
    try:
        manifest = fetch_manifest()
    except Exception as e:
        print(msg(f"!!! manifest 取得失敗: {e}",
                  f"!!! Failed to fetch manifest: {e}"), file=sys.stderr)
        sys.exit(1)

    rows = gather_prebuilt(manifest)
    if not rows:
        print(msg("配布データがありません。", "No distributed data."))
        return

    est = build_estimate_prebuilt(rows)
    need_rows = [r for r in rows if not r["held"]]

    for r in rows:
        state = (msg("取得済み", "held") if r["held"]
                 else msg(f"未取得 ({fmt_bytes(r['need_bytes'])})",
                          f"needed ({fmt_bytes(r['need_bytes'])})"))
        print(f"  {r['label']} {r['year']}: {state}")

    if list_only:
        return
    if not need_rows:
        print(msg("すべて取得済み。", "Everything is up to date."))
        return

    print(msg(f"ダウンロード合計: {fmt_bytes(est['total'])} "
              f"(空き: {fmt_bytes(est['free'])})",
              f"Total download: {fmt_bytes(est['total'])} "
              f"(free: {fmt_bytes(est['free'])})"))
    if dry_run:
        print(msg("[dry-run] ここで終了します。", "[dry-run] Stopping here."))
        return
    if est["free"] < est["total"]:
        print(msg("!!! 空き容量不足のため中断します。",
                  "!!! Not enough free disk space; aborting."),
              file=sys.stderr)
        sys.exit(1)
    if not yes:
        ans = input(msg("ダウンロードを実行しますか? [y/N]: ",
                        "Proceed with download? [y/N]: ")).strip().lower()
        if ans != "y":
            print(msg("中止しました。", "Cancelled."))
            return

    files = [f for r in need_rows for f in r["files"] if f["need"]]
    for i, f in enumerate(files, 1):
        print(f"  [{i}/{len(files)}] {f['name']} ({fmt_bytes(f['size'])})",
              flush=True)
        download_file(f)
    print(msg("==== 完了 ====", "==== Done ===="))


if __name__ == "__main__":
    main()
