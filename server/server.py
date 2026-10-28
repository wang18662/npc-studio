"""NPC Studio · AI 参数档案服务（零依赖，仅标准库）。

只做一件事：读写「AI 参数档案」，附带 schema/adapter 定义与版本历史。

用法（项目根目录执行）：
    python server/server.py
    浏览器打开 http://127.0.0.1:8765/profiles

历史说明：
    早期版本还有「运行时演示页」和「状态机编辑器」，它们跑的是 Python 里的
    另一套状态机，与 UE 的 StateTree 无关，会误导使用者（以为改那里就能影响
    游戏）。2026-10-28 按用户要求删除，只保留真实生效的参数档案这一条链路。
"""

import csv
import hashlib
import io
import json
import re
import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = Path(__file__).resolve().parent / "static"

PROFILES_CSV = ROOT / "profiles" / "ai_profiles.csv"
HISTORY_DIR = ROOT / "profiles" / "history"
SCHEMAS_DIR = ROOT / "schemas"
ADAPTERS_DIR = ROOT / "adapters"

HOST = "127.0.0.1"
PORT = 8765

HISTORY_LIMIT = 50
HISTORY_FILE_PATTERN = re.compile(r"^\d{8}-\d{6}-\d{3}\.csv$")


# ============================================================
# 档案读写
# ============================================================


def load_profiles() -> list:
    """读取参数档案表（同时也是 UE DataTable 的导入格式）。"""
    if not PROFILES_CSV.exists():
        return []
    with PROFILES_CSV.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def save_profiles(rows: list) -> None:
    if not rows:
        return

    PROFILES_CSV.parent.mkdir(parents=True, exist_ok=True)

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    new_bytes = buffer.getvalue().encode("utf-8")

    current = PROFILES_CSV.read_bytes() if PROFILES_CSV.exists() else b""

    # 内容没变化：不写盘，也不产生历史
    if new_bytes == current:
        return

    # 覆盖前先把旧内容存一份
    if current:
        backup_bytes(current)

    PROFILES_CSV.write_bytes(new_bytes)


# ============================================================
# 版本历史
# ============================================================


def backup_bytes(content: bytes) -> str:
    """把一段内容存成历史版本。

    按内容去重：历史里已经有一模一样的内容就不再新增。
    否则「A→B→A→B」来回回滚会不断堆重复版本。
    """
    if not content:
        return None

    HISTORY_DIR.mkdir(parents=True, exist_ok=True)

    digest = hashlib.sha256(content).hexdigest()
    for path in HISTORY_DIR.glob("*.csv"):
        try:
            if hashlib.sha256(path.read_bytes()).hexdigest() == digest:
                return None
        except OSError:
            continue

    # 毫秒精度：同一秒内多次保存也能保证文件名字典序 == 时间序
    target = HISTORY_DIR / f"{datetime.now().strftime('%Y%m%d-%H%M%S-%f')[:-3]}.csv"

    for _ in range(5):
        if not target.exists():
            break
        target = HISTORY_DIR / f"{datetime.now().strftime('%Y%m%d-%H%M%S-%f')[:-3]}.csv"
    else:
        return None

    target.write_bytes(content)
    prune_history()
    return target.name


def prune_history() -> None:
    """只保留最近 HISTORY_LIMIT 份，避免无限增长。"""
    if not HISTORY_DIR.exists():
        return
    files = sorted(HISTORY_DIR.glob("*.csv"), reverse=True)
    for stale in files[HISTORY_LIMIT:]:
        stale.unlink(missing_ok=True)


def dedupe_history() -> int:
    """清理历史里内容重复的文件（保留最新的那份）。返回删除数量。"""
    if not HISTORY_DIR.exists():
        return 0

    seen = set()
    removed = 0

    for path in sorted(HISTORY_DIR.glob("*.csv"), reverse=True):
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            continue

        if digest in seen:
            path.unlink(missing_ok=True)
            removed += 1
        else:
            seen.add(digest)

    return removed


def list_history() -> list:
    if not HISTORY_DIR.exists():
        return []

    items = []
    for path in sorted(HISTORY_DIR.glob("*.csv"), reverse=True)[:HISTORY_LIMIT]:
        try:
            with path.open(encoding="utf-8-sig", newline="") as f:
                rows = list(csv.DictReader(f))
        except Exception:  # noqa: BLE001
            rows = []

        items.append(
            {
                "file": path.name,
                "stamp": path.stem,
                "size": path.stat().st_size,
                "count": len(rows),
                "names": [r.get("Name", "") for r in rows],
            }
        )
    return items


def rollback_profiles(filename: str) -> dict:
    if not HISTORY_FILE_PATTERN.fullmatch(filename):
        return {"ok": False, "reason": f"非法文件名：{filename}"}

    target = HISTORY_DIR / filename
    if not target.exists():
        return {"ok": False, "reason": f"版本不存在：{filename}"}

    target_content = target.read_bytes()
    current = PROFILES_CSV.read_bytes() if PROFILES_CSV.exists() else b""

    if target_content == current:
        return {"ok": True, "file": filename, "note": "内容相同，无需回滚"}

    # 回滚前先把当前内容也备份，回滚本身也能再撤回
    if current:
        backup_bytes(current)

    PROFILES_CSV.write_bytes(target_content)
    return {"ok": True, "file": filename}


# ============================================================
# Schema / Adapter
# ============================================================


def list_schemas() -> list:
    result = []
    if not SCHEMAS_DIR.exists():
        return result
    for path in sorted(SCHEMAS_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        result.append(
            {
                "id": data.get("id"),
                "title": data.get("title"),
                "version": data.get("version"),
                "fieldCount": len(data.get("fields", [])),
                "groupCount": len(data.get("groups", [])),
            }
        )
    return result


def load_schema(schema_id: str) -> dict:
    if not SCHEMAS_DIR.exists():
        return None
    for path in SCHEMAS_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if data.get("id") == schema_id:
            return data
    return None


def load_adapter(adapter_id: str) -> dict:
    path = ADAPTERS_DIR / f"{adapter_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


# ============================================================
# HTTP
# ============================================================


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:  # 静默访问日志
        pass

    def _query(self, key: str, default=None):
        from urllib.parse import parse_qs, urlparse

        parsed = parse_qs(urlparse(self.path).query)
        return (parsed.get(key) or [default])[0]

    def _send(self, body: bytes, mime: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", f"{mime}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, data: dict) -> None:
        self._send(json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json")

    def _redirect(self, location: str) -> None:
        self.send_response(302)
        self.send_header("Location", location)
        self.end_headers()

    def do_GET(self) -> None:
        path = self.path.split("?")[0]

        if path in ("/", "/index.html"):
            self._redirect("/profiles")
        elif path == "/profiles":
            self._send((STATIC / "profiles.html").read_bytes(), "text/html")
        elif path == "/static/profiles.css":
            self._send((STATIC / "profiles.css").read_bytes(), "text/css")
        elif path == "/static/profiles.js":
            self._send((STATIC / "profiles.js").read_bytes(), "application/javascript")
        elif path == "/api/profiles":
            self._send_json({"rows": load_profiles()})
        elif path == "/api/profiles/export":
            rows = load_profiles()
            if not rows:
                self.send_error(404, "没有档案可导出")
                return
            buffer = io.StringIO()
            writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
            # 无 BOM：UE 的 CSV 导入对 BOM 敏感
            self._send(buffer.getvalue().encode("utf-8"), "text/csv")
        elif path == "/api/profiles/history":
            self._send_json({"items": list_history()})
        elif path == "/api/profiles/history/download":
            filename = self._query("file", "")
            if not HISTORY_FILE_PATTERN.fullmatch(filename):
                self.send_error(400, "非法文件名")
                return
            target = HISTORY_DIR / filename
            if not target.exists():
                self.send_error(404, "版本不存在")
                return
            self._send(target.read_bytes(), "text/csv")
        elif path == "/api/schemas":
            self._send_json({"schemas": list_schemas()})
        elif path == "/api/schema":
            schema_id = self._query("id", "npc.pursue")
            data = load_schema(schema_id)
            if data is None:
                self.send_error(404, f"schema not found: {schema_id}")
                return
            self._send_json(data)
        elif path == "/api/adapters":
            adapters = []
            if ADAPTERS_DIR.exists():
                for adapter_path in sorted(ADAPTERS_DIR.glob("*.json")):
                    try:
                        item = json.loads(adapter_path.read_text(encoding="utf-8"))
                    except json.JSONDecodeError:
                        continue
                    adapters.append(
                        {
                            "id": item.get("id"),
                            "displayName": item.get("displayName"),
                            "schemaId": item.get("schemaId"),
                        }
                    )
            self._send_json({"adapters": adapters})
        elif path == "/api/adapter":
            adapter_id = self._query("id", "shooterai")
            data = load_adapter(adapter_id)
            if data is None:
                self.send_error(404, f"adapter not found: {adapter_id}")
                return
            self._send_json(data)
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            self.send_error(400)
            return

        if self.path == "/api/profiles":
            rows = body.get("rows") or []
            save_profiles(rows)
            self._send_json({"ok": True, "count": len(rows)})
        elif self.path == "/api/profiles/rollback":
            result = rollback_profiles(str(body.get("file", "")))
            self._send_json(result)
        else:
            self.send_error(404)


def main() -> None:
    removed = dedupe_history()
    if removed:
        print(f"清理了 {removed} 个重复的历史版本")

    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"NPC Studio 参数档案：http://{HOST}:{PORT}/profiles")
    print("按 Ctrl+C 停止")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
        server.shutdown()


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    main()
