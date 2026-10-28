"""加载指定 NPC 并展示继承解析结果。

用法（在项目根目录执行）：
    python tools/load_npc.py               # 默认 guard_base
    python tools/load_npc.py elite_guard   # 继承示例
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config_loader import ConfigLoader, summarize  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def get_by_path(obj, path: str):
    """按点号路径读取。穿过数组时用下一段作为元素的 id 查找。"""
    cur = obj
    for key in path.split("."):
        if isinstance(cur, list):
            match = next(
                (item for item in cur if isinstance(item, dict) and item.get("id") == key),
                None,
            )
            if match is None:
                raise KeyError(key)
            cur = match
        else:
            cur = cur[key]
    return cur


def main() -> None:
    npc_id = sys.argv[1] if len(sys.argv) > 1 else "guard_base"

    loader = ConfigLoader(ROOT)
    resolved, provenance = loader.load_with_provenance(npc_id)
    stats = summarize(resolved, loader.project)

    # 继承链
    chain = []
    cur = npc_id
    while cur:
        chain.append(cur)
        cur = loader.load_raw(cur).get("extends")
    chain.reverse()

    print(f"NPC   : {resolved['name']} ({resolved['npcId']})")
    print(f"继承链: {' -> '.join(chain)}")
    print(f"标签  : {', '.join(resolved.get('tags', []))}")
    print()

    print("层与状态（解析后）：")
    for layer in stats["layers"]:
        if not layer["count"]:
            print(f"  {layer['id']:<12} 未配置")
            continue
        names = "、".join(layer["names"])
        print(f"  {layer['id']:<12} {layer['count']} 个  (初始 {layer['initial']})  -> {names}")
    print(f"  合计 {stats['total']} 个状态")
    print()

    identity = {"npcId", "name", "schemaVersion", "tags", "meta"}
    local = {
        path: source
        for path, source in provenance.items()
        if source == npc_id and path not in identity and not path.startswith("meta.")
    }

    if local:
        print(f"本地覆盖的字段（共 {len(local)} 处）：")
        for path in sorted(local):
            print(f"  {path} = {get_by_path(resolved, path)}")
        print()

        if npc_id != "guard_base":
            print("与父级 guard_base 对比：")
            base = loader.load("guard_base")
            for path in sorted(local):
                try:
                    old = get_by_path(base, path)
                except (KeyError, TypeError):
                    old = "<父级无此字段>"
                print(f"  {path}")
                print(f"    父级: {old}")
                print(f"    本级: {get_by_path(resolved, path)}")
    else:
        print("本地覆盖的字段：无（完全继承父级）")


if __name__ == "__main__":
    main()
