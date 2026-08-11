#!/usr/bin/env python3
"""
make_data_release.py - 構築済みデータのローリングリリース更新（メンテナ用）

ローカル data/*.json から manifest.json を生成し、GitHub Releases の
ローリングリリース（タグ data-latest）へ gh CLI でアップロードする。
利用者側は fetch_prebuilt.py / update.html がこのリリースを参照する。

既にリリース上にあり内容が変わっていないアセットは送り直さない。判定は
公開中の manifest.json の sha256 と、リリース上のアセットのサイズの両方が
ローカルと一致すること。前者だけだと中断で切れたアセットを見逃し、
後者だけだと同サイズの別内容を見逃すため、両方を見る。

使い方:
  python3 make_data_release.py --dry-run   # 対象一覧と送信予定の確認のみ
  python3 make_data_release.py             # 差分のみアップロード
  python3 make_data_release.py --prune     # リリース上の不要アセットも削除
  python3 make_data_release.py --force     # 変更が無いものも含めて全件送り直す

前提: gh CLI 導入済み・認証済み（gh auth status）
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HEATMAP_DIR = Path(__file__).resolve().parent
DATA_DIR = HEATMAP_DIR / "data"
TAG = "data-latest"
REPO = "kondou/propmap"
MANIFEST_URL = f"https://github.com/{REPO}/releases/download/{TAG}/manifest.json"

_FILE_RE = re.compile(r"^[a-z_]+_\d{4}(_approx|_rbn|_rbn_approx)?\.json$")

# 6GB規模を一度に上げるとGitHub側が散発的に 502 を返す。失敗したら間を置いて
# 数回やり直す（ここで諦めると manifest 未更新のまま不整合が残る）。
UPLOAD_RETRIES = 5
RETRY_WAIT_SEC = 15


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def build_manifest() -> dict:
    files = []
    for p in sorted(DATA_DIR.glob("*.json")):
        if not _FILE_RE.match(p.name):
            continue
        files.append({"name": p.name, "size": p.stat().st_size,
                      "sha256": sha256_of(p)})
    return {"generated": datetime.now(timezone.utc)
                                 .strftime("%Y-%m-%dT%H:%M:%SZ"),
            "files": files}


def gh(*args, check=True, capture=False):
    r = subprocess.run(["gh", *args], text=True,
                       capture_output=capture, cwd=HEATMAP_DIR)
    if check and r.returncode != 0:
        sys.exit(f"gh {' '.join(args)} failed (rc={r.returncode})")
    return r


def release_asset_sizes() -> dict:
    """リリース上のアセット名→サイズ。リリースが無ければ空。"""
    r = gh("release", "view", TAG, "--json", "assets",
           check=False, capture=True)
    if r.returncode != 0:
        return {}
    return {a["name"]: a["size"] for a in json.loads(r.stdout)["assets"]}


def published_manifest() -> dict:
    """公開中の manifest.json の name→sha256。取れなければ空。"""
    try:
        with urllib.request.urlopen(MANIFEST_URL, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return {f["name"]: f["sha256"] for f in data.get("files", [])}
    except Exception as e:
        print(f"  note: 公開中の manifest を取得できず全件送信します ({e})")
        return {}


def upload(path: Path) -> bool:
    for attempt in range(1, UPLOAD_RETRIES + 1):
        r = gh("release", "upload", TAG, str(path), "--clobber",
               check=False, capture=True)
        if r.returncode == 0:
            return True
        tail = (r.stderr or "").strip().splitlines()[-1:] or [""]
        print(f"      retry {attempt}/{UPLOAD_RETRIES}: {tail[0][:120]}")
        if attempt < UPLOAD_RETRIES:
            time.sleep(RETRY_WAIT_SEC)
    return False


def main():
    ap = argparse.ArgumentParser(description="Update the data-latest release")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--prune", action="store_true",
                    help="delete release assets no longer present locally")
    ap.add_argument("--force", action="store_true",
                    help="upload every file even if unchanged")
    args = ap.parse_args()

    manifest = build_manifest()
    total = sum(f["size"] for f in manifest["files"])
    print(f"data files: {len(manifest['files'])}  total: {total:,} bytes")
    if not manifest["files"]:
        sys.exit("no data files found; aborting")

    existing = release_asset_sizes()
    remote_sha = {} if args.force else published_manifest()

    todo = []
    for f in manifest["files"]:
        unchanged = (not args.force
                     and remote_sha.get(f["name"]) == f["sha256"]
                     and existing.get(f["name"]) == f["size"])
        if not unchanged:
            todo.append(f)
    skipped = len(manifest["files"]) - len(todo)
    print(f"upload: {len(todo)} file(s), {sum(f['size'] for f in todo):,} bytes"
          f"   (unchanged: {skipped})")

    if args.dry_run:
        for f in todo:
            print(f"  {f['name']}  {f['size']:,}")
        print("[dry-run] no upload")
        return

    if not existing and gh("release", "view", TAG,
                           check=False, capture=True).returncode != 0:
        print(f"creating release {TAG} ...")
        gh("release", "create", TAG, "--title", "PropMap data (rolling)",
           "--notes",
           "Rolling release of pre-built heatmap data. "
           "Fetched by update.html / fetch_prebuilt.py. "
           "Assets are overwritten in place; do not rely on permanence.")

    with tempfile.TemporaryDirectory() as td:
        mpath = Path(td) / "manifest.json"
        mpath.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
        # データ本体を先に、manifest を最後に上げる（不整合窓を最小化）
        failed = []
        for i, f in enumerate(todo, 1):
            print(f"[{i}/{len(todo)}] upload {f['name']}")
            if not upload(DATA_DIR / f["name"]):
                failed.append(f["name"])
        if failed:
            # manifest を上げてしまうと、実体が古いまま新しい sha256 を指す
            # 状態になり、利用者側の検証が通らなくなる
            print(f"\n{len(failed)} file(s) failed; manifest not updated:")
            for n in failed:
                print("  " + n)
            sys.exit("aborted (re-run to retry only the remaining files)")
        print("upload manifest.json")
        if not upload(mpath):
            sys.exit("manifest upload failed")

    if args.prune:
        keep = {f["name"] for f in manifest["files"]} | {"manifest.json"}
        for name in sorted(set(release_asset_sizes()) - keep):
            print(f"prune {name}")
            gh("release", "delete-asset", TAG, name, "--yes")

    print("done")


if __name__ == "__main__":
    main()
