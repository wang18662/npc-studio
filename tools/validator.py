"""配置校验器：结构校验（B4）+ 语义校验（B5）。

规则编号对应 NPC-Studio-配置规范.md 第 9 节。
B5 阶段实现：V003 / V004 / V005 / V006 / V008 / V009。
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

import jsonschema

from config_loader import (
    CircularInheritance,
    ConfigError,
    ConfigLoader,
    InheritanceTooDeep,
)


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


@dataclass
class Issue:
    level: str  # error | warning
    rule: str
    path: str
    message: str

    def __str__(self) -> str:
        return f"[{self.level:<7}] {self.rule:<6} {self.path}: {self.message}"


@dataclass
class Report:
    npc_id: str
    issues: list = field(default_factory=list)

    def error(self, rule: str, path: str, message: str) -> None:
        self.issues.append(Issue("error", rule, path, message))

    def warning(self, rule: str, path: str, message: str) -> None:
        self.issues.append(Issue("warning", rule, path, message))

    @property
    def errors(self) -> list:
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> list:
        return [i for i in self.issues if i.level == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors


class Validator:
    """把「结构校验」与「语义校验」分开，各自用不同的输入。"""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.loader = ConfigLoader(root)
        self.project = self.loader.project
        self.schema = load_json(self.root / "schema" / "npc.schema.json")
        self.capabilities = {c["id"] for c in self.project["capabilities"]}
        self.param_definitions = self.project.get("paramDefinitions", {})

    def validate(self, npc_id: str) -> Report:
        report = Report(npc_id)

        # 读取原始文件（结构校验的对象）
        try:
            raw = self.loader.load_raw(npc_id)
        except ConfigError as err:
            report.error("V002", "-", str(err))
            return report

        self._check_schema(raw, report)

        # 解析继承（语义校验的对象）
        try:
            resolved, _ = self.loader.load_with_provenance(npc_id)
        except CircularInheritance as err:
            report.error("V006", "extends", str(err))
            return report
        except InheritanceTooDeep as err:
            report.error("V007", "extends", str(err))
            return report
        except ConfigError as err:
            report.error("V006", "extends", str(err))
            return report

        self._check_layers(resolved, report)
        self._check_params(resolved, report)
        self._check_ai(resolved, report)
        self._check_reachability(resolved, report)

        # V001：schemaVersion 与项目一致
        if raw.get("schemaVersion") != self.project.get("schemaVersion"):
            report.error(
                "V001",
                "schemaVersion",
                f"文件为 {raw.get('schemaVersion')}，项目为 {self.project.get('schemaVersion')}",
            )

        return report

    # ---------- B4：结构校验 ----------

    def _check_schema(self, raw: dict, report: Report) -> None:
        validator = jsonschema.Draft7Validator(self.schema)
        for err in sorted(validator.iter_errors(raw), key=lambda e: list(e.path)):
            path = ".".join(str(p) for p in err.path) or "<root>"
            report.error("SCHEMA", path, err.message)

    # ---------- B5：语义校验 ----------

    def _check_layers(self, resolved: dict, report: Report) -> None:
        for layer_id, layer in resolved.get("layers", {}).items():
            base = f"layers.{layer_id}"
            states = layer.get("states", [])
            state_ids = [s["id"] for s in states]

            # V003：层内 state.id 唯一
            seen = set()
            for state in states:
                if state["id"] in seen:
                    report.error("V003", f"{base}.states.{state['id']}", f"状态 id 重复：{state['id']}")
                seen.add(state["id"])

            # V005：initialState 必须存在
            if layer.get("initialState") not in state_ids:
                report.error(
                    "V005",
                    f"{base}.initialState",
                    f"初始状态 {layer.get('initialState')} 不存在于本层",
                )

            for state in states:
                spath = f"{base}.states.{state['id']}"

                # V004：转移目标必须在同层存在
                for index, transition in enumerate(state.get("transitions", [])):
                    target = transition.get("to")
                    if target not in state_ids:
                        report.error(
                            "V004",
                            f"{spath}.transitions[{index}]",
                            f"转移目标 {target} 不在本层，或不存在",
                        )

                requires = set(state.get("requires", []))
                locks = set(state.get("locks", []))

                # V008：能力必须在项目能力表中
                for cap in sorted(requires | locks):
                    if cap not in self.capabilities:
                        report.error("V008", spath, f"未知能力：{cap}")

                # V009：同一能力不能既 requires 又 locks
                overlap = requires & locks
                if overlap:
                    report.error(
                        "V009",
                        spath,
                        f"同一能力不能既 requires 又 locks：{', '.join(sorted(overlap))}",
                    )

    # ---------- B6：参数 / AI / 可达性 ----------

    def _check_params(self, resolved: dict, report: Report) -> None:
        """V010 参数类型与范围；V016 参数未在定义表中。"""
        for layer_id, layer in resolved.get("layers", {}).items():
            for state in layer.get("states", []):
                spath = f"layers.{layer_id}.states.{state['id']}"
                archetype = state.get("archetype")
                specs = self.param_definitions.get(archetype)

                if specs is None:
                    report.warning("V016", spath, f"原型 `{archetype}` 没有参数定义表")
                    continue

                for name, value in state.get("params", {}).items():
                    if name not in specs:
                        report.warning(
                            "V016",
                            f"{spath}.params.{name}",
                            f"参数 `{name}` 未在原型 `{archetype}` 的定义表中",
                        )
                        continue
                    self._check_param_value(name, value, specs[name], f"{spath}.params.{name}", report)

    def _check_param_value(self, name: str, value, spec: dict, path: str, report: Report) -> None:
        ptype = spec.get("type")
        type_ok = {
            "float": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
            "int": lambda v: isinstance(v, int) and not isinstance(v, bool),
            "bool": lambda v: isinstance(v, bool),
            "string": lambda v: isinstance(v, str),
        }.get(ptype, lambda v: True)

        if not type_ok(value):
            report.error("V010", path, f"参数 `{name}` 应为 {ptype}，实际是 {type(value).__name__}")
            return

        if ptype in ("float", "int"):
            low, high = spec.get("min"), spec.get("max")
            if low is not None and value < low:
                report.error("V010", path, f"参数 `{name}` = {value}，小于下限 {low}")
            if high is not None and value > high:
                report.error("V010", path, f"参数 `{name}` = {value}，大于上限 {high}")

    def _check_ai(self, resolved: dict, report: Report) -> None:
        """V011 工具前置状态存在；V012 意图引用的工具已授权。"""
        ai = resolved.get("ai")
        if not ai:
            return

        all_states = set()
        for layer in resolved.get("layers", {}).values():
            for state in layer.get("states", []):
                all_states.add(state["id"])

        enabled_tools = {t["name"] for t in ai.get("tools", []) if t.get("enabled")}

        for tool in ai.get("tools", []):
            for state_id in tool.get("preconditions", {}).get("requiredStates", []):
                if state_id not in all_states:
                    report.error(
                        "V011",
                        f"ai.tools.{tool['name']}",
                        f"前置状态 `{state_id}` 不存在于任何层",
                    )

        for intent in ai.get("intents", []):
            for tool_name in intent.get("allowedTools", []):
                if tool_name not in enabled_tools:
                    report.error(
                        "V012",
                        f"ai.intents.{intent['id']}",
                        f"意图引用了未授权或未启用的工具 `{tool_name}`",
                    )

    def _check_reachability(self, resolved: dict, report: Report) -> None:
        """V013 状态不可达；V014 非终止状态必须有出口。"""
        for layer_id, layer in resolved.get("layers", {}).items():
            initial = layer.get("initialState")
            targeted = set()
            for state in layer.get("states", []):
                for transition in state.get("transitions", []):
                    targeted.add(transition["to"])

            for state in layer.get("states", []):
                if state["id"] != initial and state["id"] not in targeted:
                    report.warning(
                        "V013",
                        f"layers.{layer_id}.states.{state['id']}",
                        f"状态「{state['name']}」不可达（没有任何转移指向它）",
                    )

                # V014：没有出口且未标记 terminal 视为错误
                if not state.get("terminal") and not state.get("transitions"):
                    report.error(
                        "V014",
                        f"layers.{layer_id}.states.{state['id']}",
                        f"状态「{state['name']}」没有出口转移，也未标记 terminal",
                    )
