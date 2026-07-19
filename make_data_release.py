#!/usr/bin/env python3
"""
make_data_release.py - 構築済みデータのローリングリリース更新（メンテナ用）

ローカル data/*.json から manifest.json を生成し、GitHub Releases の
ローリングリリース（タグ data-latest）へ gh CLI でアップロードする。
利用者側は fetch_prebuilt.py / update.html がこのリリースを参照する。

使い方:
  python3 make_data_release.py --dry-run   # 対象一覧と manifest 内容の確認のみ
  python3 make_data_release.py             # manifest 生成 + アップロード
  python3 make_data_release.py --prune     # リリース上の不要アセットも削除

前提: gh CLI 導入済み・認証済み（gh auth status）
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

HEATMAP_DIR = Path(__file__).resolve().parent
DATA_DIR = HEATMAP_DIR / "data"
TAG = "data-latest"

_FILE_RE = re.compile(r"^[a-z_]+_\d{4}(_approx|_rbn|_rbn_approx)?\.json$")


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
                       capture_output=capture)
    if check and r.returncode != 0:
        sys.exit(f"gh {' '.join(args)} failed (rc={r.returncode})")
    return r


def release_assets() -> set:
    r = gh("release", "view", TAG, "--json", "assets",
           check=False, capture=True)
    if r.returncode != 0:
        return set()
    return {a["name"] for a in json.loads(r.stdout)["assets"]}


def main():
    ap = argparse.ArgumentParser(description="Update the data-latest release")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--prune", action="store_true",
                    help="delete release assets no longer present locally")
    args = ap.parse_args()

    manifest = build_manifest()
    total = sum(f["size"] for f in manifest["files"])
    print(f"data files: {len(manifest['files'])}  total: {total:,} bytes")
    if not manifest["files"]:
        sys.exit("no data files found; aborting")

    if args.dry_run:
        for f in manifest["files"]:
            print(f"  {f['name']}  {f['size']:,}")
        print("[dry-run] no upload")
        return

    existing = release_assets()
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
        names = [f["name"] for f in manifest["files"]]
        for i, name in enumerate(names, 1):
            print(f"[{i}/{len(names)}] upload {name}")
            gh("release", "upload", TAG, str(DATA_DIR / name), "--clobber")
        print("upload manifest.json")
        gh("release", "upload", TAG, str(mpath), "--clobber")

    if args.prune:
        keep = {f["name"] for f in manifest["files"]} | {"manifest.json"}
        for name in sorted(release_assets() - keep):
            print(f"prune {name}")
            gh("release", "delete-asset", TAG, name, "--yes")

    print("done")


if __name__ == "__main__":
    main()
