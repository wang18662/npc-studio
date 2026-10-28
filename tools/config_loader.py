"""配置加载器：读取 NPC 配置并解析继承。

对应实施步骤 B1（ConfigLoader）与 B2（继承解析）。

设计依据：NPC-Studio-配置规范.md 第 7 节
- 继承用 extends + overrides
- 覆盖路径用点号
- 数组整体替换，不做逐项合并
- 继承层数 ≤ 3，禁止循环
"""

import copy
import json
from pathlib import Path

MAX_INHERIT_DEPTH = 3


class ConfigError(Exception):
    """配置错误基类。"""


class NpcNotFound(ConfigError):
    """找不到 NPC 文件。"""


class CircularInheritance(ConfigError):
    """检测到循环继承。"""


class InheritanceTooDeep(ConfigError):
    """继承层数超过上限。"""


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def set_path(obj: dict, path: str, value) -> None:
    """按点号路径写入嵌套字典。

    路径穿过数组时，用路径中的下一段作为元素的 `id` 查找。
    例如 `layers.locomotion.states.s_chase.params.speed`
    会在 states 数组里找 id == "s_chase" 的元素。

    路径中间节点必须已存在，否则报错——避免「写到一个不存在的字段」这种沉默错误。
    """
    keys = path.split(".")
    cur = obj

    for key in keys[:-1]:
        if isinstance(cur, list):
            match = next(
                (item for item in cur if isinstance(item, dict) and item.get("id") == key),
                None,
            )
            if match is None:
                raise ConfigError(f"覆盖路径无效：{path}（数组中没有 id={key} 的元素）")
            cur = match
            continue

        if key not in cur:
            raise ConfigError(f"覆盖路径无效：{path}（在 `{key}` 处中断）")
        cur = cur[key]

    if isinstance(cur, list):
        raise ConfigError(f"覆盖路径无效：{path}（末尾不能直接指向数组，请指定元素）")

    cur[keys[-1]] = copy.deepcopy(value)


def collect_leaf_paths(obj, prefix: str = "") -> list:
    """收集所有叶子路径。数组视为一个整体（因为规范规定数组整体替换）。"""
    if isinstance(obj, dict):
        paths = []
        for key, value in obj.items():
            child = f"{prefix}.{key}" if prefix else key
            paths.extend(collect_leaf_paths(value, child))
        return paths
    return [prefix]


class ConfigLoader:
    """读取项目配置与 NPC 配置，并解析继承关系。"""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.project = load_json(self.root / "project.json")
        self._raw_cache: dict = {}
        self._resolved_cache: dict = {}

    # ---------- B1：读取 ----------

    def load_raw(self, npc_id: str) -> dict:
        """读取原始文件，不做继承解析。"""
        if npc_id in self._raw_cache:
            return self._raw_cache[npc_id]

        path = self.root / "npcs" / f"{npc_id}.json"
        if not path.exists():
            raise NpcNotFound(f"找不到 NPC 配置：{path}")

        data = load_json(path)
        if data.get("npcId") != npc_id:
            raise ConfigError(
                f"文件名与 npcId 不一致：文件名 {npc_id}，文件内 {data.get('npcId')}"
            )

        self._raw_cache[npc_id] = data
        return data

    # ---------- B2：继承解析 ----------

    def load(self, npc_id: str) -> dict:
        """加载并解析继承，返回最终配置。"""
        if npc_id in self._resolved_cache:
            return self._resolved_cache[npc_id]
        resolved, _ = self._resolve(npc_id, chain=[])
        self._resolved_cache[npc_id] = resolved
        return resolved

    def load_with_provenance(self, npc_id: str) -> tuple:
        """加载并返回（最终配置, 字段来源表）。

        来源表形如 {"layers.combat.states.s_attack.params.damage": "elite_guard"}，
        供编辑器显示「继承自 X」/「本地覆盖」。
        """
        return self._resolve(npc_id, chain=[])

    def _resolve(self, npc_id: str, chain: list) -> tuple:
        if npc_id in chain:
            raise CircularInheritance(f"循环继承：{' -> '.join(chain + [npc_id])}")
        if len(chain) > MAX_INHERIT_DEPTH:
            raise InheritanceTooDeep(
                f"继承层数超过 {MAX_INHERIT_DEPTH}：{' -> '.join(chain + [npc_id])}"
            )

        raw = self.load_raw(npc_id)
        parent_id = raw.get("extends")

        # 无继承：直接返回自身
        if not parent_id:
            resolved = copy.deepcopy(raw)
            provenance = {path: npc_id for path in collect_leaf_paths(resolved)}
            return resolved, provenance

        # 递归解析父级
        parent_resolved, parent_provenance = self._resolve(parent_id, chain + [npc_id])
        resolved = copy.deepcopy(parent_resolved)
        provenance = dict(parent_provenance)

        # 应用 overrides
        for path, value in raw.get("overrides", {}).items():
            set_path(resolved, path, value)
            provenance[path] = npc_id

        # 身份字段始终用子级的，不允许被父级覆盖
        for field in ("schemaVersion", "npcId", "name", "tags", "meta"):
            if field in raw:
                resolved[field] = copy.deepcopy(raw[field])
                for path in collect_leaf_paths({field: resolved[field]}):
                    provenance[path] = npc_id

        # 继承字段已解析完毕，从结果中移除
        resolved.pop("extends", None)
        resolved.pop("overrides", None)
        provenance.pop("extends", None)
        provenance.pop("overrides", None)

        return resolved, provenance


def summarize(resolved: dict, project: dict) -> dict:
    """统计层与状态，供测试脚本输出。"""
    layers = []
    total = 0
    for layer_id in project["layers"]:
        layer = resolved["layers"].get(layer_id)
        if not layer:
            layers.append({"id": layer_id, "count": 0, "initial": None, "names": []})
            continue
        names = [state["name"] for state in layer["states"]]
        total += len(names)
        layers.append(
            {
                "id": layer_id,
                "count": len(names),
                "initial": layer["initialState"],
                "names": names,
            }
        )
    return {"layers": layers, "total": total}
