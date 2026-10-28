"""能力锁（C3 / C4）。

规则（与配置规范一致）：
- requires 与 locks 都按「排他占用」处理
- 一个能力同一时刻只能被一个状态持有
- 转移时先尝试占用新状态需要的能力，成功后才释放旧状态不再需要的部分
- 等待超过 timeout 时强制夺取并记录告警（防死锁）
"""


class CapabilityLock:
    def __init__(self, timeout: float = 5.0):
        self.timeout = timeout
        self._owner = {}
        self._since = {}
        self._priority = {}
        self.warnings = []

    def try_acquire(
        self,
        owner_id: str,
        requires,
        locks,
        now: float,
        takeover: str = None,
        priority: int = 0,
    ) -> bool:
        """原子性占用：全部可获得才占，否则一个都不占。

        - takeover：允许从同层旧状态接管（同层是替换关系）
        - priority：优先级高于占用者时，可以抢占
        """
        need = set(requires) | set(locks)

        for cap in need:
            holder = self._owner.get(cap)
            if holder is None or holder == owner_id:
                continue
            if takeover is not None and holder == takeover:
                continue
            if priority > self._priority.get(holder, 0):
                continue
            return False

        for cap in need:
            holder = self._owner.get(cap)
            if holder == owner_id:
                self._priority[owner_id] = priority
                continue

            # 同层接管属于正常替换，不算抢占
            is_takeover = takeover is not None and holder == takeover
            if holder is not None and not is_takeover:
                self.warnings.append(
                    f"[{now:.1f}s] {owner_id}(p={priority}) 抢占 "
                    f"{holder}(p={self._priority.get(holder, 0)}) 的能力 {cap}"
                )

            self._owner[cap] = owner_id
            self._priority[owner_id] = priority
            self._since[cap] = now
        return True

    def force_take(self, owner_id: str, caps, now: float, priority: int = 999) -> None:
        """等待超时后强制夺取。"""
        for cap in caps:
            previous = self._owner.get(cap)
            if previous and previous != owner_id:
                self.warnings.append(
                    f"[{now:.1f}s] 能力 {cap} 被 {previous} 占用超时，强制转给 {owner_id}"
                )
            self._owner[cap] = owner_id
            self._priority[owner_id] = priority
            self._since[cap] = now

    def release_cap(self, cap: str, owner_id: str) -> None:
        if self._owner.get(cap) == owner_id:
            self._owner.pop(cap, None)
            self._since.pop(cap, None)

    def release_owner(self, owner_id: str) -> None:
        for cap in [c for c, o in self._owner.items() if o == owner_id]:
            self._owner.pop(cap, None)
            self._since.pop(cap, None)
        self._priority.pop(owner_id, None)

    def holders(self) -> dict:
        return dict(self._owner)

    def held_duration(self, now: float) -> dict:
        return {cap: round(now - since, 1) for cap, since in self._since.items()}

    def is_locked(self, cap: str) -> bool:
        return cap in self._owner
