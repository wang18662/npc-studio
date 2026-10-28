"""状态定义与条件表达式求值（C1）。"""

import re
from dataclasses import dataclass, field


class SafeContext(dict):
    """条件求值上下文。

    - 未定义的 `on_xxx` 视为 False（事件未发生）
    - 其他未定义变量直接报错，避免拼写错误被静默吞掉
    """

    def __missing__(self, key):
        if key.startswith("on_"):
            return False
        raise KeyError(f"条件表达式引用了未定义的变量：{key}")


def evaluate(expr: str, ctx: dict) -> bool:
    """把配置里的条件表达式转成 Python 表达式求值。

    支持的写法：
        distance(player) < 8
        self.hp < 30
        time_in_state > 10
        on_player_interact
        (a || b) && !c
    """
    normalized = expr.replace("&&", " and ").replace("||", " or ")
    normalized = re.sub(r"!(?!=)", " not ", normalized)

    try:
        return bool(eval(normalized, {"__builtins__": {}}, SafeContext(ctx)))
    except KeyError:
        raise
    except Exception as err:  # noqa: BLE001
        raise ValueError(f"条件表达式求值失败：{expr}（{err}）") from err


@dataclass
class Transition:
    to: str
    priority: int
    condition: str
    cooldown: float = 0.0
    interruptible: bool = True
    emit: str = None


@dataclass
class State:
    id: str
    name: str
    archetype: str
    requires: list = field(default_factory=list)
    locks: list = field(default_factory=list)
    params: dict = field(default_factory=dict)
    transitions: list = field(default_factory=list)
    terminal: bool = False
    priority: int = 0
    behavior_tree: dict = None
    on_enter: list = field(default_factory=list)
    on_exit: list = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "State":
        return cls(
            id=data["id"],
            name=data["name"],
            archetype=data["archetype"],
            requires=list(data.get("requires", [])),
            locks=list(data.get("locks", [])),
            params=dict(data.get("params", {})),
            transitions=[
                Transition(
                    to=t["to"],
                    priority=t["priority"],
                    condition=t["condition"],
                    cooldown=t.get("cooldown", 0.0),
                    interruptible=t.get("interruptible", True),
                    emit=t.get("emit"),
                )
                for t in data.get("transitions", [])
            ],
            terminal=data.get("terminal", False),
            priority=data.get("priority", 0),
            behavior_tree=data.get("behaviorTree"),
            on_enter=list(data.get("onEnter", [])),
            on_exit=list(data.get("onExit", [])),
        )

    @property
    def capabilities(self) -> set:
        """该状态需要占用的全部能力（requires 与 locks 都按排他处理）。"""
        return set(self.requires) | set(self.locks)

    def sorted_transitions(self) -> list:
        """按优先级降序排列。"""
        return sorted(self.transitions, key=lambda t: -t.priority)
