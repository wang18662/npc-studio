"""NPC Studio 本地演示服务器（零依赖，仅用标准库）。

用法（在项目根目录执行）：
    python server/server.py
    浏览器打开 http://127.0.0.1:8765

说明：为了让项目零依赖运行，这里用「HTTP 轮询」代替 WebSocket。
前端每 100ms 拉一次状态，对演示来说足够流畅。
"""

import csv
import io
import json
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = Path(__file__).resolve().parent / "static"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from config_loader import ConfigLoader  # noqa: E402
from runtime.ai_gateway import AIGateway  # noqa: E402
from runtime.knowledge import KnowledgeBase  # noqa: E402
from runtime.npc_runtime import NpcRuntime, World  # noqa: E402
from runtime.tool_executor import ToolExecutor  # noqa: E402
from validator import Validator  # noqa: E402

HOST = "127.0.0.1"
PORT = 8765
DT = 0.1
NPC_ID = "guard_base"

loader = ConfigLoader(ROOT)
config = loader.load(NPC_ID)
world = World(npc_pos=(10.0, 10.0))
world.player_pos = (4.0, 4.0)
npc = NpcRuntime(config, loader.project, world)

ai_config = config.get("ai", {})
knowledge = KnowledgeBase(ROOT, ai_config.get("knowledgeBase", "guard_faq"))
tool_executor = ToolExecutor()
gateway = AIGateway(ai_config, knowledge, tool_executor)

lock = threading.Lock()


def game_loop() -> None:
    while True:
        with lock:
            npc.tick(DT)
        time.sleep(DT)


def build_state() -> dict:
    with lock:
        all_logs = []
        for layer in npc.layers.values():
            all_logs.extend(layer.transitions_log)
        all_logs.sort(key=lambda item: item["time"])
        history = [
            {
                "time": round(item["time"], 1),
                "layer": item["layer"],
                "from": item["from"],
                "to": item["to"],
                "emit": item.get("emit"),
            }
            for item in all_logs[-8:]
        ]

        return {
            "time": round(npc.time, 1),
            "npcId": NPC_ID,
            "player": {"x": round(world.player_pos[0], 2), "y": round(world.player_pos[1], 2)},
            "npc": {"x": world.npc_pos[0], "y": world.npc_pos[1]},
            "distance": round(world.distance("player"), 2),
            "layers": {
                layer_id: {
                    "state": layer.current.name,
                    "id": layer.current.id,
                    "time": round(layer.time_in_state, 1),
                    "priority": layer.current.priority,
                }
                for layer_id, layer in npc.layers.items()
            },
            "locks": npc.locks(),
            "events": sorted(npc.bus.last_frame),
            "history": history,
            "tools": {
                "flags": dict(tool_executor.flags),
                "recent": tool_executor.log[-5:],
            },
            "ai": {"mode": gateway.mode, "hasKey": bool(gateway.api_key)},
        }


NPC_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")

LAYER_NAMES = {"locomotion": "移动层", "interaction": "交互层", "combat": "战斗层"}

PROFILES_CSV = ROOT / "profiles" / "ai_profiles.csv"
SCHEMAS_DIR = ROOT / "schemas"
ADAPTERS_DIR = ROOT / "adapters"


def list_schemas() -> list:
    """列出所有可用的 schema。"""
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


def load_profiles() -> list:
    """读取 AI 参数档案表（同时也是 UE DataTable 的导入格式）。"""
    if not PROFILES_CSV.exists():
        return []
    with PROFILES_CSV.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def save_profiles(rows: list) -> None:
    if not rows:
        return
    PROFILES_CSV.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())
    with PROFILES_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def export_datatable(config: dict) -> str:
    """扁平化为 CSV，每行一个状态（对应配置规范 10.2）。"""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["StateId", "Name", "Layer", "Archetype", "Priority", "Requires", "Locks", "Transitions", "Params"]
    )

    for layer_id, layer in config.get("layers", {}).items():
        for state in layer.get("states", []):
            transitions = ";".join(
                f"{t['to']}:{t['priority']}:{t['condition']}"
                for t in state.get("transitions", [])
            )
            writer.writerow(
                [
                    state["id"],
                    state["name"],
                    layer_id,
                    state["archetype"],
                    state.get("priority", 0),
                    ";".join(state.get("requires", [])),
                    ";".join(state.get("locks", [])),
                    transitions,
                    json.dumps(state.get("params", {}), ensure_ascii=False),
                ]
            )
    return buffer.getvalue()


def export_doc(config: dict) -> str:
    """从配置生成 Markdown 手册（G6）。"""
    lines = [f"# {config['name']} · 配置手册", ""]
    lines.append(f"- npcId: `{config['npcId']}`")
    lines.append(f"- 继承: `{config.get('extends') or '无'}`")

    attributes = config.get("attributes", {})
    if attributes:
        lines.append("- 属性: " + "、".join(f"{k}={v}" for k, v in attributes.items()))
    lines.append("")

    for layer_id, layer in config.get("layers", {}).items():
        lines.append(f"## {LAYER_NAMES.get(layer_id, layer_id)}")
        lines.append("")
        lines.append(f"初始状态：`{layer['initialState']}`")
        lines.append("")
        lines.append("| 状态 | ID | 原型 | 优先级 | 需要能力 | 锁定能力 |")
        lines.append("|---|---|---|---|---|---|")
        for state in layer.get("states", []):
            lines.append(
                f"| {state['name']} | `{state['id']}` | {state['archetype']} | "
                f"{state.get('priority', 0)} | "
                f"{', '.join(state.get('requires', [])) or '—'} | "
                f"{', '.join(state.get('locks', [])) or '—'} |"
            )
        lines.append("")

        lines.append("### 状态转移")
        lines.append("")
        lines.append("| 从 | 到 | 优先级 | 条件 | 发出事件 |")
        lines.append("|---|---|---|---|---|")
        for state in layer.get("states", []):
            for transition in state.get("transitions", []):
                lines.append(
                    f"| {state['name']} | `{transition['to']}` | {transition['priority']} | "
                    f"`{transition['condition']}` | {transition.get('emit') or '—'} |"
                )
        lines.append("")

    ai = config.get("ai")
    if ai:
        lines.append("## AI 配置")
        lines.append("")
        lines.append("| 意图 | 示例 | 知识片段 | 可用工具 |")
        lines.append("|---|---|---|---|")
        for intent in ai.get("intents", []):
            lines.append(
                f"| {intent['name']} | {'、'.join(intent.get('examples', []))} | "
                f"{', '.join(intent.get('knowledgeRefs', [])) or '—'} | "
                f"{', '.join(intent.get('allowedTools', [])) or '—'} |"
            )
        lines.append("")

    return "\n".join(lines)


def save_npc(npc_id: str, config: dict) -> dict:
    """写回配置文件并跑校验。"""
    if not NPC_ID_PATTERN.fullmatch(npc_id):
        return {"ok": False, "issues": [], "reason": f"非法 npcId：{npc_id}"}

    path = ROOT / "npcs" / f"{npc_id}.json"
    config["npcId"] = npc_id
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # 清掉加载器缓存，让后续读取拿到新内容
    loader._raw_cache.clear()
    loader._resolved_cache.clear()

    report = Validator(ROOT).validate(npc_id)
    return {
        "ok": report.ok,
        "issues": [
            {"level": i.level, "rule": i.rule, "path": i.path, "message": i.message}
            for i in report.issues
        ],
        "note": "已写入文件；运行时状态需重启服务器后生效",
    }


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

    def do_GET(self) -> None:
        path = self.path.split("?")[0]

        if path in ("/", "/index.html"):
            self._send((STATIC / "index.html").read_bytes(), "text/html")
        elif path == "/static/style.css":
            self._send((STATIC / "style.css").read_bytes(), "text/css")
        elif path == "/static/game.js":
            self._send((STATIC / "game.js").read_bytes(), "application/javascript")
        elif path == "/api/state":
            self._send_json(build_state())
        elif path == "/profiles":
            self._send((STATIC / "profiles.html").read_bytes(), "text/html")
        elif path == "/static/profiles.css":
            self._send((STATIC / "profiles.css").read_bytes(), "text/css")
        elif path == "/static/profiles.js":
            self._send((STATIC / "profiles.js").read_bytes(), "application/javascript")
        elif path == "/api/profiles":
            self._send_json({"rows": load_profiles()})
        elif path == "/api/schemas":
            self._send_json({"schemas": list_schemas()})
        elif path == "/api/schema":
            schema_id = self._query("id", "npc.pursue")
            data = load_schema(schema_id)
            if data is None:
                self.send_error(404, f"schema not found: {schema_id}")
                return
            self._send_json(data)
        elif path == "/api/adapter":
            adapter_id = self._query("id", "shooterai")
            data = load_adapter(adapter_id)
            if data is None:
                self.send_error(404, f"adapter not found: {adapter_id}")
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
        elif path == "/api/profiles/export":
            rows = load_profiles()
            if not rows:
                self.send_error(404, "没有档案可导出")
                return
            buffer = io.StringIO()
            writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
            # 用无 BOM 的 UTF-8：UE 的 CSV 导入对 BOM 敏感
            self._send(buffer.getvalue().encode("utf-8"), "text/csv")
        elif path == "/editor":
            self._send((STATIC / "editor.html").read_bytes(), "text/html")
        elif path == "/static/editor.css":
            self._send((STATIC / "editor.css").read_bytes(), "text/css")
        elif path == "/static/editor.js":
            self._send((STATIC / "editor.js").read_bytes(), "application/javascript")
        elif path == "/api/npc/raw":
            npc_id = self._query("npcId", NPC_ID)
            try:
                raw = loader.load_raw(npc_id)
            except Exception as err:  # noqa: BLE001
                self.send_error(404, str(err))
                return
            self._send_json(raw)
        elif path == "/api/export/datatable":
            npc_id = self._query("npcId", NPC_ID)
            try:
                config_data = loader.load(npc_id)
            except Exception as err:  # noqa: BLE001
                self.send_error(404, str(err))
                return
            self._send(export_datatable(config_data).encode("utf-8-sig"), "text/csv")
        elif path == "/api/export/doc":
            npc_id = self._query("npcId", NPC_ID)
            try:
                config_data = loader.load(npc_id)
            except Exception as err:  # noqa: BLE001
                self.send_error(404, str(err))
                return
            self._send(export_doc(config_data).encode("utf-8"), "text/markdown")
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

        if self.path == "/api/move":
            with lock:
                world.player_pos = (float(body.get("x", 0)), float(body.get("y", 0)))
            self._send_json({"ok": True})
        elif self.path == "/api/interact":
            with lock:
                npc.bus.emit("player_interact")
            self._send_json({"ok": True})
        elif self.path == "/api/end-dialogue":
            with lock:
                npc.bus.emit("dialogue_end")
            self._send_json({"ok": True})
        elif self.path == "/api/chat":
            message = str(body.get("message", "")).strip()
            if not message:
                self._send_json({"reply": "……", "intent": None, "tool": None})
                return

            with lock:
                interaction = npc.layers.get("interaction")
                ctx = {
                    "current_state": interaction.current.id if interaction else None,
                    "owner": interaction.current.id if interaction else None,
                    "locks": npc.locks(),
                    "flags": tool_executor.flags,
                    "emit": npc.bus.emit,
                }
                result = gateway.chat(message, ctx)
            self._send_json(result)
        elif self.path == "/api/npc/save":
            npc_id = str(body.get("npcId", NPC_ID))
            config_data = body.get("config") or {}
            with lock:
                result = save_npc(npc_id, config_data)
            self._send_json(result)
        elif self.path == "/api/profiles":
            rows = body.get("rows") or []
            save_profiles(rows)
            self._send_json({"ok": True, "count": len(rows)})
        else:
            self.send_error(404)


def main() -> None:
    threading.Thread(target=game_loop, daemon=True).start()

    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"NPC Studio 演示已启动：http://{HOST}:{PORT}")
    print("按 Ctrl+C 停止")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
        server.shutdown()


if __name__ == "__main__":
    main()
