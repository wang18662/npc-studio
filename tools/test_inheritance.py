"""继承解析的边界测试（B2 验收补充）。

用法：
    python tools/test_inheritance.py
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config_loader import (  # noqa: E402
    CircularInheritance,
    ConfigError,
    ConfigLoader,
    InheritanceTooDeep,
)


def make_project(root: Path) -> None:
    (root / "project.json").write_text(
        json.dumps(
            {
                "schemaVersion": "1.0.0",
                "projectId": "test",
                "projectName": "Test",
                "layers": ["locomotion"],
                "capabilities": [{"id": "Move", "description": ""}],
                "capabilityConflictPolicy": "lock",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def write_npc(root: Path, npc_id: str, data: dict) -> None:
    (root / "npcs").mkdir(parents=True, exist_ok=True)
    (root / "npcs" / f"{npc_id}.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )


def base_npc(npc_id: str, extends: str = None, overrides: dict = None) -> dict:
    data = {
        "schemaVersion": "1.0.0",
        "npcId": npc_id,
        "name": npc_id,
        "overrides": overrides or {},
    }
    if extends:
        data["extends"] = extends
    else:
        data["layers"] = {
            "locomotion": {
                "initialState": "s_a",
                "states": [
                    {
                        "id": "s_a",
                        "name": "A",
                        "archetype": "idle",
                        "params": {"speed": 1.0},
                        "transitions": [],
                    }
                ],
            }
        }
    return data


def expect(label: str, fn, exc_type) -> None:
    try:
        fn()
    except exc_type as err:
        print(f"[通过] {label}：{type(err).__name__} - {err}")
        return
    except Exception as err:  # noqa: BLE001
        print(f"[失败] {label}：抛出了错误的异常 {type(err).__name__} - {err}")
        return
    print(f"[失败] {label}：没有抛出异常")


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_project(root)

        # 1. 循环继承
        write_npc(root, "a", base_npc("a", extends="b"))
        write_npc(root, "b", base_npc("b", extends="a"))
        loader = ConfigLoader(root)
        expect("循环继承被拦截", lambda: loader.load("a"), CircularInheritance)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_project(root)

        # 2. 继承层数超过 3
        write_npc(root, "n0", base_npc("n0"))
        for i in range(1, 5):
            write_npc(root, f"n{i}", base_npc(f"n{i}", extends=f"n{i - 1}"))
        loader = ConfigLoader(root)
        expect("继承过深被拦截", lambda: loader.load("n4"), InheritanceTooDeep)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_project(root)

        # 3. 覆盖路径不存在
        write_npc(root, "p0", base_npc("p0"))
        write_npc(root, "p1", base_npc("p1", extends="p0", overrides={"layers.locomotion.states.s_zzz.params.speed": 9}))
        loader = ConfigLoader(root)
        expect("无效覆盖路径被拦截", lambda: loader.load("p1"), ConfigError)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_project(root)

        # 4. 正常继承
        write_npc(root, "q0", base_npc("q0"))
        write_npc(
            root,
            "q1",
            base_npc(
                "q1",
                extends="q0",
                overrides={"layers.locomotion.states.s_a.params.speed": 7.5},
            ),
        )
        loader = ConfigLoader(root)
        resolved = loader.load("q1")
        speed = resolved["layers"]["locomotion"]["states"][0]["params"]["speed"]
        if speed == 7.5:
            print(f"[通过] 正常继承并覆盖：speed = {speed}")
        else:
            print(f"[失败] 覆盖结果不对：speed = {speed}")

        # 5. 缓存一致性：改父级后重新加载不应串味
        again = loader.load("q0")
        base_speed = again["layers"]["locomotion"]["states"][0]["params"]["speed"]
        if base_speed == 1.0:
            print(f"[通过] 父级配置未被污染：speed = {base_speed}")
        else:
            print(f"[失败] 父级被污染：speed = {base_speed}")


if __name__ == "__main__":
    main()
