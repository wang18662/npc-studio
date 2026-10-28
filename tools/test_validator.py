"""校验器的规则测试（B5 验收）。

为每条规则构造一个错误样本，验证能被拦截。

用法：
    python tools/test_validator.py
"""

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from validator import Validator  # noqa: E402

REAL_ROOT = Path(__file__).resolve().parent.parent


def make_project(root: Path) -> None:
    (root / "schema").mkdir(parents=True, exist_ok=True)
    (root / "npcs").mkdir(parents=True, exist_ok=True)
    shutil.copy(
        REAL_ROOT / "schema" / "npc.schema.json",
        root / "schema" / "npc.schema.json",
    )
    (root / "project.json").write_text(
        json.dumps(
            {
                "schemaVersion": "1.0.0",
                "projectId": "test",
                "projectName": "Test",
                "layers": ["locomotion"],
                "capabilities": [
                    {"id": "Move", "description": ""},
                    {"id": "Attack", "description": ""},
                ],
                "paramDefinitions": {
                    "idle": {},
                    "movement": {
                        "speed": {"type": "float", "min": 0, "max": 20, "default": 3.0},
                        "radius": {"type": "float", "min": 0, "max": 50, "default": 5.0},
                    },
                    "combat": {},
                    "interaction": {},
                    "perception": {},
                    "special": {},
                },
                "capabilityConflictPolicy": "lock",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def state(sid, requires=None, locks=None, transitions=None, archetype="idle", params=None):
    return {
        "id": sid,
        "name": sid,
        "archetype": archetype,
        "requires": requires or [],
        "locks": locks or [],
        "params": params or {},
        "transitions": transitions or [],
    }


def npc(npc_id, states, initial="s_a", extra=None):
    data = {
        "schemaVersion": "1.0.0",
        "npcId": npc_id,
        "name": npc_id,
        "layers": {"locomotion": {"initialState": initial, "states": states}},
    }
    if extra:
        data.update(extra)
    return data


def write_npc(root: Path, npc_id: str, data: dict) -> None:
    (root / "npcs" / f"{npc_id}.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )


def check(label: str, root: Path, npc_id: str, rule: str) -> None:
    report = Validator(root).validate(npc_id)
    hit = [issue for issue in report.errors if issue.rule == rule]
    if hit:
        print(f"[通过] {label}  ->  {rule}")
        print(f"        {hit[0]}")
    else:
        actual = [issue.rule for issue in report.errors] or "无错误"
        print(f"[失败] {label}  ->  期望 {rule}，实际 {actual}")


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_project(root)

        # V003：层内 state.id 重复
        write_npc(root, "dup", npc("dup", [state("s_a"), state("s_a")]))
        check("状态 id 重复", root, "dup", "V003")

        # V004：转移目标不存在
        bad_transition = state("s_a", transitions=[{"to": "s_missing", "priority": 1, "condition": "true"}])
        write_npc(root, "bad_to", npc("bad_to", [bad_transition]))
        check("转移目标不存在", root, "bad_to", "V004")

        # V005：initialState 不存在
        write_npc(root, "bad_initial", npc("bad_initial", [state("s_a")], initial="s_none"))
        check("初始状态不存在", root, "bad_initial", "V005")

        # V006：extends 指向不存在的 NPC
        write_npc(
            root,
            "bad_parent",
            {
                "schemaVersion": "1.0.0",
                "npcId": "bad_parent",
                "name": "bad_parent",
                "extends": "not_exist",
                "overrides": {},
            },
        )
        check("父级不存在", root, "bad_parent", "V006")

        # V008：未知能力
        write_npc(root, "bad_cap", npc("bad_cap", [state("s_a", requires=["Fly"])]))
        check("未知能力", root, "bad_cap", "V008")

        # V009：requires 与 locks 重叠
        write_npc(root, "overlap", npc("overlap", [state("s_a", requires=["Move"], locks=["Move"])]))
        check("能力重复声明", root, "overlap", "V009")

        # 正确样本：不应报错
        write_npc(
            root,
            "good",
            npc(
                "good",
                [
                    state("s_a", requires=["Move"], locks=["Attack"], transitions=[{"to": "s_b", "priority": 1, "condition": "true"}]),
                    state("s_b", requires=["Attack"], locks=["Move"], transitions=[{"to": "s_a", "priority": 1, "condition": "true"}]),
                ],
            ),
        )
        report = Validator(root).validate("good")
        if report.ok:
            print("[通过] 正确样本  ->  无错误")
        else:
            print(f"[失败] 正确样本  ->  误报：{[str(i) for i in report.errors]}")

        # V010：参数超范围
        write_npc(
            root,
            "bad_range",
            npc("bad_range", [state("s_a", archetype="movement", params={"speed": 999})]),
        )
        check("参数超范围", root, "bad_range", "V010")

        # V010：参数类型错误
        write_npc(
            root,
            "bad_type",
            npc("bad_type", [state("s_a", archetype="movement", params={"speed": "fast"})]),
        )
        check("参数类型错误", root, "bad_type", "V010")

        # V011：工具前置状态不存在
        write_npc(
            root,
            "bad_tool",
            npc(
                "bad_tool",
                [state("s_a")],
                extra={
                    "ai": {
                        "enabled": True,
                        "model": "x",
                        "intents": [],
                        "tools": [
                            {
                                "name": "give_quest",
                                "enabled": True,
                                "preconditions": {"requiredStates": ["s_zz"]},
                            }
                        ],
                    }
                },
            ),
        )
        check("工具前置状态不存在", root, "bad_tool", "V011")

        # V012：意图引用未授权工具
        write_npc(
            root,
            "bad_intent",
            npc(
                "bad_intent",
                [state("s_a")],
                extra={
                    "ai": {
                        "enabled": True,
                        "model": "x",
                        "intents": [
                            {
                                "id": "i1",
                                "name": "n",
                                "examples": ["x"],
                                "fallback": "f",
                                "allowedTools": ["open_door"],
                            }
                        ],
                        "tools": [],
                    }
                },
            ),
        )
        check("意图引用未授权工具", root, "bad_intent", "V012")

        # V013：状态不可达（warning）
        write_npc(root, "unreachable", npc("unreachable", [state("s_a"), state("s_b")]))
        report = Validator(root).validate("unreachable")
        hits = [i for i in report.warnings if i.rule == "V013"]
        print(f"[{'通过' if hits else '失败'}] 状态不可达  ->  V013")
        if hits:
            print(f"        {hits[0]}")

        # V016：参数未在定义表（warning）
        write_npc(
            root,
            "unknown_param",
            npc("unknown_param", [state("s_a", archetype="movement", params={"flySpeed": 5})]),
        )
        report = Validator(root).validate("unknown_param")
        hits = [i for i in report.warnings if i.rule == "V016"]
        print(f"[{'通过' if hits else '失败'}] 参数未定义  ->  V016")
        if hits:
            print(f"        {hits[0]}")

        # V014：非终止状态没有出口
        write_npc(root, "no_exit", npc("no_exit", [state("s_a")]))
        check("无出口且非终止", root, "no_exit", "V014")

        # V014：终止状态允许没有出口
        end_state = state("s_end")
        end_state["terminal"] = True
        write_npc(root, "terminal_ok", npc("terminal_ok", [end_state]))
        report = Validator(root).validate("terminal_ok")
        hits = [i for i in report.errors if i.rule == "V014"]
        print(f"[{'通过' if not hits else '失败'}] 终止状态无出口  ->  不报 V014")


if __name__ == "__main__":
    main()
