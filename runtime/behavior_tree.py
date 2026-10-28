"""行为树执行器（C6）。

只负责「状态内的动作编排」，不做状态切换——这是与状态机的边界。
返回值为 success / failure / running。
"""

from .state import evaluate


def run(node: dict, ctx: dict, action_runner=None) -> str:
    if not node:
        return "success"

    kind = node.get("type")

    if kind == "selector":
        for child in node.get("children", []):
            result = run(child, ctx, action_runner)
            if result != "failure":
                return result
        return "failure"

    if kind == "sequence":
        for child in node.get("children", []):
            result = run(child, ctx, action_runner)
            if result != "success":
                return result
        return "success"

    if kind == "condition":
        return "success" if evaluate(node["expr"], ctx) else "failure"

    if kind == "action":
        if action_runner is None:
            return "success"
        return action_runner(node.get("name"), node.get("params", {}))

    raise ValueError(f"未知的行为树节点类型：{kind}")
