"""事件总线（C7）。

事件在两帧之间的传递规则：
- emit 把事件放进 pending
- 每层 tick 前调用 merge_pending，把 pending 并入当帧可见集合
- 帧末调用 end_frame 清空

这样 locomotion 层在同一帧发出的事件，后面的 combat 层就能看到。
"""


class EventBus:
    def __init__(self):
        self._pending = []
        self._current = set()
        self.last_frame = set()
        self.history = []

    def emit(self, name: str) -> None:
        if name:
            self._pending.append(name)
            self.history.append(name)

    def merge_pending(self) -> None:
        """把待处理事件并入当前帧可查询集合。"""
        if self._pending:
            self._current |= set(self._pending)
            self._pending.clear()

    def end_frame(self) -> None:
        self.last_frame = set(self._current)
        self._current.clear()

    def has(self, name: str) -> bool:
        return name in self._current

    def snapshot(self) -> set:
        return set(self._current)
