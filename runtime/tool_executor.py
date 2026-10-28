"""工具执行器（E5）：六步校验链。

顺序：
    1. 注册表 —— 工具是否存在
    2. 白名单 —— 当前意图是否允许调用
    3. 状态   —— 当前状态是否允许调用
    4. 能力   —— 需要的能力是否被别的状态占用
    5. 标记   —— 全局前置条件是否满足
    6. 执行   —— 真正执行并发出事件

任何一步失败都返回结构化原因（failedAt + reason），
让上层（LLM）知道为什么失败，而不是只拿到一个 false。
"""


class ToolExecutor:
    def __init__(self):
        self.flags = {}
        self.log = []
        self._impl = {
            "give_quest": self._give_quest,
            "open_door": self._open_door,
            "trade": self._trade,
            "give_item": self._give_item,
            "summon_ally": self._summon_ally,
            "heal": self._heal,
            "apply_buff": self._apply_buff,
            "flee": self._flee,
        }

    def known_tools(self) -> set:
        return set(self._impl)

    def request(self, name: str, args: dict, config: dict, ctx: dict) -> dict:
        # ① 注册表
        impl = self._impl.get(name)
        if impl is None:
            return self._fail("registry", f"未知工具：{name}")

        preconditions = (config or {}).get("preconditions", {})

        # ② 白名单
        allowed = ctx.get("allowed_tools")
        if allowed is not None and name not in allowed:
            return self._fail("whitelist", f"当前意图未授权调用 {name}")

        # ③ 状态前置
        required_states = preconditions.get("requiredStates", [])
        current = ctx.get("current_state")
        if required_states and current not in required_states:
            return self._fail("state", f"当前状态 {current} 不允许调用 {name}")

        # ④ 能力锁
        locks = ctx.get("locks", {})
        owner = ctx.get("owner")
        for cap in preconditions.get("requiredCapabilities", []):
            holder = locks.get(cap)
            if holder and holder != owner:
                return self._fail("capability", f"能力 {cap} 正被 {holder} 占用")

        # ⑤ 全局标记
        for flag in preconditions.get("requiredFlags", []):
            if not self.flags.get(flag):
                return self._fail("flag", f"缺少前置条件：{flag}")

        # ⑥ 执行 + 事件
        result = impl(args, ctx)
        emit = ctx.get("emit")
        if emit:
            emit(f"tool_{name}")

        self.log.append({"tool": name, "args": args, "result": result})
        return {"ok": True, "tool": name, "result": result}

    @staticmethod
    def _fail(stage: str, reason: str) -> dict:
        return {"ok": False, "failedAt": stage, "reason": reason}

    # ---------- 内置工具实现 ----------

    def _give_quest(self, args, ctx):
        quest_id = args.get("questId", "quest_gate_patrol")
        self.flags[f"quest_{quest_id}_given"] = True
        return {"questId": quest_id, "title": "西门的麻烦", "hint": "去广场北边找村长"}

    def _open_door(self, args, ctx):
        door_id = args.get("doorId", "gate_west")
        self.flags[f"door_{door_id}_open"] = True
        return {"doorId": door_id, "opened": True}

    def _trade(self, args, ctx):
        return {
            "itemId": args.get("itemId", "potion"),
            "price": args.get("price", 10),
            "traded": True,
        }

    def _give_item(self, args, ctx):
        item_id = args.get("itemId", "bread")
        count = args.get("count", 1)
        self.flags[f"item_{item_id}_given"] = True
        return {"itemId": item_id, "count": count}

    def _summon_ally(self, args, ctx):
        count = args.get("count", 2)
        self.flags["ally_summoned"] = True
        return {"count": count, "message": f"叫来了 {count} 名巡逻兵"}

    def _heal(self, args, ctx):
        return {"target": args.get("target", "self"), "amount": args.get("amount", 20)}

    def _apply_buff(self, args, ctx):
        return {"target": args.get("target", "self"), "buffId": args.get("buffId", "guard_aura")}

    def _flee(self, args, ctx):
        self.flags["fled"] = True
        return {"fled": True}
