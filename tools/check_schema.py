"""检查 schema 与 adapter 的一致性。

这一步不改任何代码，纯粹验证「通用语义键 + 映射表」这套设计能不能成立。

用法：
    python tools/check_schema.py
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    schema = load(ROOT / "schemas" / "npc.pursue.json")
    adapter = load(ROOT / "adapters" / "shooterai.json")

    schema_keys = [f["key"] for f in schema["fields"]]
    schema_key_set = set(schema_keys)
    mapping = adapter["mapping"]
    map_keys = set(mapping.keys())

    print("=" * 62)
    print(f"Schema : {schema['id']}   （{len(schema_keys)} 个字段）")
    print(f"Adapter: {adapter['id']}  （{len(map_keys)} 条映射）")
    print("=" * 62)

    ok = True

    # 1. schema 内部重复
    dup = {k for k in schema_keys if schema_keys.count(k) > 1}
    if dup:
        ok = False
        print(f"[错误] Schema 内有重复 key：{dup}")

    # 2. schema → adapter 缺失
    missing = [k for k in schema_keys if k not in map_keys]
    if missing:
        ok = False
        print(f"[缺失] 以下字段在 adapter 里没有映射（{len(missing)} 个）：")
        for key in missing:
            print(f"    {key}")
    else:
        print("[通过] Schema 的每个字段都有映射")

    # 3. adapter 多余
    extra = map_keys - schema_key_set
    if extra:
        print(f"[多余] adapter 映射了 schema 没有的字段（{len(extra)} 个）：")
        for key in sorted(extra):
            print(f"    {key}")
    else:
        print("[通过] adapter 没有多余映射")

    # 4. 分组引用检查
    group_ids = {g["id"] for g in schema["groups"]}
    bad_groups = [f["key"] for f in schema["fields"] if f["group"] not in group_ids]
    if bad_groups:
        ok = False
        print(f"[错误] 以下字段的 group 不存在：{bad_groups}")
    else:
        print("[通过] 所有字段的 group 都存在")

    # 5. 约束表达式里的字段引用
    print()
    print(f"约束 {len(schema['constraints'])} 条：")
    for constraint in schema["constraints"]:
        refs = re.findall(r"[a-z]+\.[a-zA-Z]+", constraint["expr"])
        unknown = [r for r in refs if r not in schema_key_set]
        if unknown:
            ok = False
            print(f"  {constraint['id']}  [错误] 引用了未知字段：{unknown}")
        else:
            print(f"  {constraint['id']}  [通过] {constraint['expr']}")

    # 6. 映射名重复检查（两个通用键映射到同一个引擎字段）
    targets = list(mapping.values())
    dup_targets = {t for t in targets if targets.count(t) > 1}
    print()
    if dup_targets:
        ok = False
        print(f"[错误] 多个通用键映射到同一个引擎字段：{dup_targets}")
    else:
        print("[通过] 映射目标无重复")

    print()
    print("=" * 62)
    print("结论：设计成立，可以开始改代码" if ok else "结论：有问题，先修复上面标红的项")
    print("=" * 62)


if __name__ == "__main__":
    main()
