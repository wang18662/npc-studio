"""Day 1 / A5：验证配置能被读取并解析。

用法（在项目根目录执行）：
    python tools/load_test.py
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def validate(path: Path, data: dict) -> None:
    """若安装了 jsonschema，则做一次结构校验（B4 阶段会升级为完整校验器）。"""
    try:
        import jsonschema
    except ImportError:
        print("[跳过] 未安装 jsonschema，跳过结构校验。安装：pip install jsonschema")
        return

    schema = load_json(ROOT / "schema" / "npc.schema.json")
    validator = jsonschema.Draft7Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))

    if not errors:
        print(f"[通过] {path.name} 结构校验无错误")
        return

    print(f"[失败] {path.name} 有 {len(errors)} 处结构错误：")
    for err in errors:
        location = ".".join(str(p) for p in err.path) or "<root>"
        print(f"  - {location}: {err.message}")


def main() -> None:
    project = load_json(ROOT / "project.json")
    npc_path = ROOT / "npcs" / "guard_base.json"
    npc = load_json(npc_path)

    print(f"项目：{project['projectName']} ({project['projectId']})")
    print(f"NPC ：{npc['name']} ({npc['npcId']})")
    caps = [c["id"] for c in project["capabilities"]]
    print(f"能力：{len(caps)} 种 -> {', '.join(caps)}")
    print()

    validate(npc_path, npc)
    print()

    total = 0
    print("层与状态：")
    for layer_id in project["layers"]:
        layer = npc["layers"].get(layer_id)
        if not layer:
            print(f"  {layer_id:<12} 未配置")
            continue
        states = layer["states"]
        total += len(states)
        names = "、".join(s["name"] for s in states)
        print(f"  {layer_id:<12} {len(states)} 个状态  (初始 {layer['initialState']})  -> {names}")

    print()
    print(f"合计 {total} 个状态")
    print()

    print("能力锁占用：")
    for layer_id, layer in npc["layers"].items():
        for state in layer["states"]:
            if state.get("locks"):
                print(f"  [{layer_id}] {state['name']} 锁住 -> {', '.join(state['locks'])}")


if __name__ == "__main__":
    main()
