"""单层状态机（C2）。

每层独立 tick，按 priority 降序检查转移条件；转移必须通过能力锁。
事件通过 EventBus 跨层传递，不直接改其他层的状态。
"""

from .state import State, evaluate


class LayerMachine:
    def __init__(self, layer_id: str, config: dict, lock, bus):
        self.layer_id = layer_id
        self.states = {s["id"]: State.from_dict(s) for s in config["states"]}

        initial_id = config["initialState"]
        if initial_id not in self.states:
            raise ValueError(f"层 {layer_id} 的初始状态 {initial_id} 不存在")

        self.current = self.states[initial_id]
        self.lock = lock
        self.bus = bus
        self.time_in_state = 0.0
        self._cooldowns = {}
        self._wait_time = 0.0
        self._pending = None  # (transition, target)：因能力被占而挂起的转移
        self.transitions_log = []

        # 进入初始状态需要占用能力；被占用则强制夺取（启动阶段不等待）
        if not self.lock.try_acquire(
            self.current.id,
            self.current.requires,
            self.current.locks,
            0.0,
            priority=self.current.priority,
        ):
            self.lock.force_take(
                self.current.id, self.current.capabilities, 0.0, priority=self.current.priority
            )
        self._fire_enter(self.current)

    def tick(self, dt: float, now: float, ctx_factory) -> None:
        self.time_in_state += dt
        for key in list(self._cooldowns):
            self._cooldowns[key] = max(0.0, self._cooldowns[key] - dt)

        # 优先处理挂起的转移：条件当时成立过，就记住它，等能力释放
        if self._pending is not None:
            transition, target = self._pending

            if self._try_transition(transition, target, now):
                self._pending = None
                self._wait_time = 0.0
                return

            self._wait_time += dt
            if self._wait_time > self.lock.timeout:
                self.lock.force_take(target.id, target.capabilities, now)
                self._wait_time = 0.0
                if self._try_transition(transition, target, now):
                    self._pending = None
            return

        for transition in self.current.sorted_transitions():
            if self._cooldowns.get(transition.to, 0.0) > 0:
                continue

            if not evaluate(transition.condition, ctx_factory(self)):
                continue

            target = self.states.get(transition.to)
            if target is None:
                continue

            if self._try_transition(transition, target, now):
                break

            # 条件成立但能力被占：挂起，下一帧继续尝试
            self._pending = (transition, target)
            self._wait_time = 0.0
            break

    def _try_transition(self, transition, target: State, now: float) -> bool:
        # 同层是「替换」关系：允许从当前状态接管能力；优先级高于占用者可抢占
        if not self.lock.try_acquire(
            target.id,
            target.requires,
            target.locks,
            now,
            takeover=self.current.id,
            priority=target.priority,
        ):
            return False

        old_caps = self.current.capabilities
        new_caps = target.capabilities
        for cap in old_caps - new_caps:
            self.lock.release_cap(cap, self.current.id)

        previous = self.current
        self._fire_exit(previous)

        self.current = target
        self.time_in_state = 0.0
        if transition.cooldown > 0:
            self._cooldowns[transition.to] = transition.cooldown
        if transition.emit:
            self.bus.emit(transition.emit)
        self._fire_enter(target)

        self.transitions_log.append(
            {
                "time": now,
                "layer": self.layer_id,
                "from": previous.name,
                "to": target.name,
                "emit": transition.emit,
            }
        )
        return True

    def _fire_enter(self, state: State) -> None:
        for event in state.on_enter:
            self.bus.emit(event)

    def _fire_exit(self, state: State) -> None:
        for event in state.on_exit:
            self.bus.emit(event)
