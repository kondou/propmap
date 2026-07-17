#!/usr/bin/env python3
"""
propmap_server.py - PropMap ローカルサーバー（静的配信 + データ更新API）

従来の `python3 -m http.server` を置き換える。標準ライブラリのみ使用。
127.0.0.1 にのみバインドする（外部からAPIを叩かれないため）。

静的配信: このファイルと同じディレクトリ（~/heatmap 相当）を配信
API:
  POST /api/new-logs/check    新規年の確認+見積もり開始（バックグラウンド）
                              body(JSON, 省略可): {"contest": str, "all_missing": bool}
  POST /api/new-logs/import   直近のcheck結果を対象に取り込み開始
  GET  /api/new-logs/status   ジョブ状態JSON
  GET  /api/datasets          data/*.json の実在一覧 {contest: [years...]}

ジョブ状態機械:
  idle → checking → ready → running → done
                  ↘ error        ↘ error
  同時に走るジョブは常に1件。実行中の check/import 要求は 409 を返す。

起動: python3 propmap_server.py [--port 8765]
"""

import argparse
import json
import re
import subprocess
import sys
import threading
import time
from collections import deque
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HEATMAP_DIR = Path(__file__).resolve().parent
SCRIPT_DIR = HEATMAP_DIR / "contest_logs"
sys.path.insert(0, str(SCRIPT_DIR))

import check_new_logs as cnl                      # noqa: E402
from contest_utils import CONTEST_CFG, msg        # noqa: E402

LOG_TAIL_LINES = 80
DATASET_RE = re.compile(r"^([a-z_]+)_(\d{4})\.json$")

# ---- ジョブ状態（単一ジョブ・ロック保護） -----------------------------------

_lock = threading.Lock()
_job = {
    "state": "idle",          # idle/checking/ready/running/done/error
    "started": None,          # epoch秒
    "finished": None,
    "params": {},             # checkに渡したパラメータ
    "targets": [],            # gather_targets の結果
    "unpublished": [],
    "estimate": None,         # build_estimate の結果
    "steps_total": 0,
    "step_index": 0,          # 1-origin（実行中のステップ番号）
    "step_label": "",
    "results": [],            # [{"contest","year","ok"}]
    "error": None,
    "log": deque(maxlen=LOG_TAIL_LINES),
    "proc": None,             # 実行中のサブプロセス（状態には含めない）
}


def _log_line(line: str):
    line = line.rstrip("\n")
    if line:
        with _lock:
            _job["log"].append(line)


def _snapshot() -> dict:
    with _lock:
        d = {k: v for k, v in _job.items() if k not in ("log", "proc")}
        d["log_tail"] = list(_job["log"])
        if _job["started"] and not _job["finished"]:
            d["elapsed_sec"] = int(time.time() - _job["started"])
        elif _job["started"] and _job["finished"]:
            d["elapsed_sec"] = int(_job["finished"] - _job["started"])
        else:
            d["elapsed_sec"] = 0
    return d


# ---- check（確認+見積もり）スレッド -----------------------------------------

def _check_worker(contests, all_missing):
    try:
        _log_line(msg("公開ログサイトを確認中...",
                      "Checking public log sites..."))
        targets, unpublished = cnl.gather_targets(contests, all_missing)
        for u in unpublished:
            _log_line(f"  {u['label']} {u['year']}: "
                      + msg("未公開", "not published yet"))
        for t in targets:
            _log_line(f"  {t['label']} {t['year']}: "
                      + msg(f"公開済み ({t['logs']:,}局)",
                            f"available ({t['logs']:,} logs)"))
        estimate = cnl.build_estimate(targets) if targets else None
        with _lock:
            _job["targets"] = targets
            _job["unpublished"] = unpublished
            _job["estimate"] = estimate
            _job["state"] = "ready"
            _job["finished"] = time.time()
    except Exception as e:
        with _lock:
            _job["state"] = "error"
            _job["error"] = f"check failed: {e}"
            _job["finished"] = time.time()


# ---- import（取り込み）スレッド ----------------------------------------------

def _run_step(cmd) -> int:
    """1ステップをサブプロセス実行し、出力をログ末尾バッファへ流す"""
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True,
                            bufsize=1, cwd=str(SCRIPT_DIR))
    with _lock:
        _job["proc"] = proc
    for line in proc.stdout:
        _log_line(line)
    proc.wait()
    with _lock:
        _job["proc"] = None
    return proc.returncode


def _import_worker(targets):
    try:
        # 空き容量ガード（CLIと同じ基準: 合計未満なら中断）
        est = cnl.build_estimate(targets)
        if est["free"] < est["total"]:
            with _lock:
                _job["state"] = "error"
                _job["error"] = msg(
                    "空き容量が見積もり合計を下回っています",
                    "Free disk space is below the estimated total")
                _job["finished"] = time.time()
            return

        all_steps = []
        for t in targets:
            for label, cmd in cnl.pipeline_steps(t["contest"], t["year"]):
                all_steps.append((t, label, cmd))
        with _lock:
            _job["steps_total"] = len(all_steps)

        failed_contest_year = set()
        results = {}
        for i, (t, label, cmd) in enumerate(all_steps, 1):
            key = (t["contest"], t["year"])
            if key in failed_contest_year:
                continue   # 前段失敗のcontest/yearは後段を実行しない
            with _lock:
                _job["step_index"] = i
                _job["step_label"] = label
            _log_line(f"==== [{i}/{len(all_steps)}] {label} ====")
            rc = _run_step(cmd)
            if rc != 0:
                _log_line(msg(f"!!! エラー (rc={rc}): {label}",
                              f"!!! Error (rc={rc}): {label}"))
                failed_contest_year.add(key)
                results[key] = False
            else:
                results.setdefault(key, True)

        with _lock:
            _job["results"] = [
                {"contest": c, "year": y, "ok": ok}
                for (c, y), ok in results.items()]
            _job["state"] = "done" if all(results.values()) else "error"
            if _job["state"] == "error":
                _job["error"] = msg("一部のステップが失敗しました（ログ参照）",
                                    "Some steps failed (see log)")
            _job["finished"] = time.time()
        _log_line(msg("==== 完了 ====", "==== Done ===="))
    except Exception as e:
        with _lock:
            _job["state"] = "error"
            _job["error"] = f"import failed: {e}"
            _job["finished"] = time.time()


# ---- HTTP ハンドラ -----------------------------------------------------------

class PropMapHandler(SimpleHTTPRequestHandler):

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(HEATMAP_DIR), **kw)

    # ログを簡潔に（静的配信の1行アクセスログは抑制、APIのみ表示）
    def log_message(self, fmt, *args):
        if self.path.startswith("/api/"):
            super().log_message(fmt, *args)

    def _host_ok(self) -> bool:
        """DNS rebinding 対策: Host が localhost 系であることを確認"""
        host = (self.headers.get("Host") or "").split(":")[0].lower()
        return host in ("localhost", "127.0.0.1", "[::1]", "::1")

    def _send_json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:
            return {}

    # ---- GET ----
    def do_GET(self):
        if not self.path.startswith("/api/"):
            return super().do_GET()
        if not self._host_ok():
            return self._send_json({"error": "forbidden host"}, 403)

        path = self.path.split("?")[0]
        if path == "/api/new-logs/status":
            return self._send_json(_snapshot())
        if path == "/api/datasets":
            return self._send_json(self._datasets())
        return self._send_json({"error": "not found"}, 404)

    def _datasets(self) -> dict:
        out = {c: [] for c in CONTEST_CFG}
        data_dir = HEATMAP_DIR / "data"
        if data_dir.is_dir():
            for p in data_dir.glob("*.json"):
                m = DATASET_RE.match(p.name)   # ベースJSONのみ対象
                if m and m.group(1) in out:
                    out[m.group(1)].append(int(m.group(2)))
        for c in out:
            out[c] = sorted(out[c])
        return out

    # ---- POST ----
    def do_POST(self):
        if not self._host_ok():
            return self._send_json({"error": "forbidden host"}, 403)
        path = self.path.split("?")[0]

        if path == "/api/new-logs/check":
            body = self._read_json_body()
            contest = body.get("contest")
            if contest is not None and contest not in CONTEST_CFG:
                return self._send_json({"error": "unknown contest"}, 400)
            all_missing = bool(body.get("all_missing"))
            with _lock:
                if _job["state"] in ("checking", "running"):
                    return self._send_json(
                        {"error": "busy", "state": _job["state"]}, 409)
                _job.update(state="checking", started=time.time(),
                            finished=None, targets=[], unpublished=[],
                            estimate=None, steps_total=0, step_index=0,
                            step_label="", results=[], error=None,
                            params={"contest": contest,
                                    "all_missing": all_missing})
                _job["log"].clear()
            contests = [contest] if contest else None
            threading.Thread(target=_check_worker,
                             args=(contests, all_missing), daemon=True).start()
            return self._send_json({"ok": True, "state": "checking"})

        if path == "/api/new-logs/import":
            with _lock:
                if _job["state"] in ("checking", "running"):
                    return self._send_json(
                        {"error": "busy", "state": _job["state"]}, 409)
                if _job["state"] != "ready" or not _job["targets"]:
                    return self._send_json(
                        {"error": "no check result; run check first"}, 400)
                targets = list(_job["targets"])
                _job.update(state="running", started=time.time(),
                            finished=None, steps_total=0, step_index=0,
                            step_label="", results=[], error=None)
            threading.Thread(target=_import_worker,
                             args=(targets,), daemon=True).start()
            return self._send_json({"ok": True, "state": "running"})

        return self._send_json({"error": "not found"}, 404)


def main():
    ap = argparse.ArgumentParser(description="PropMap local server")
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()

    srv = ThreadingHTTPServer(("127.0.0.1", args.port), PropMapHandler)
    print(msg(f"PropMap サーバー起動: http://localhost:{args.port}/heatmap.html",
              f"PropMap server: http://localhost:{args.port}/heatmap.html"))
    print(msg("データ更新ページ: "
              f"http://localhost:{args.port}/update.html",
              "Data update page: "
              f"http://localhost:{args.port}/update.html"))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
