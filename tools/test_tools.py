"""六步校验链测试（E5 验收）。

用法：
    python tools/test_tools.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from runtime.tool_executor import ToolExecutor  # noqa: E402


def show(label: str, passed: bool, detail: str) -> None:
    print(f"[{'通过' if passed else '失败'}] {label}：{detail}")


def main() -> None:
    executor = ToolExecutor()

    # ① 注册表
    result = executor.request("not_exist", {}, {}, {})
    show("未知工具被拒", result.get("failedAt") == "registry", result.get("reason", ""))

    # ② 白名单
    result = executor.request("give_quest", {}, {}, {"allowed_tools": ["open_door"]})
    show("白名单拒绝", result.get("failedAt") == "whitelist", result.get("reason", ""))

    # ③ 状态前置
    result = executor.request(
        "give_quest",
        {},
        {"preconditions": {"requiredStates": ["s_talk"]}},
        {"current_state": "s_idle"},
    )
    show("状态前置拒绝", result.get("failedAt") == "state", result.get("reason", ""))

    # ④ 能力锁
    result = executor.request(
        "summon_ally",
        {},
        {"preconditions": {"requiredCapabilities": ["Interact"]}},
        {"locks": {"Interact": "s_talk"}, "owner": "s_attack"},
    )
    show("能力占用拒绝", result.get("failedAt") == "capability", result.get("reason", ""))

    # ⑤ 全局标记
    result = executor.request(
        "open_door", {}, {"preconditions": {"requiredFlags": ["has_key"]}}, {}
    )
    show("前置标记拒绝", result.get("failedAt") == "flag", result.get("reason", ""))

    # ⑥ 成功执行 + 事件
    events = []
    result = executor.request("give_quest", {}, {}, {"emit": events.append})
    passed = bool(result.get("ok")) and "tool_give_quest" in events
    show("执行成功并派发事件", passed, f"{result.get('result')} / events={events}")

    # 标记生效：领过任务后再次调用应仍成功，但 flags 已记录
    show("工具副作用记录", "quest_quest_gate_patrol_given" in executor.flags, str(executor.flags))


if __name__ == "__main__":
    main()
