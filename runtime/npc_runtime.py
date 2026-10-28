"""NPC 运行时：三层并行调度（C5）+ 最小世界模型。

tick 顺序固定为 project.json 里 layers 的顺序，保证确定性。
"""

import math
from types import SimpleNamespace

from .capability_lock import CapabilityLock
from .event_bus import EventBus
from .layer_machine import LayerMachine


class World:
    """最小世界：只有玩家位置与 NPC 位置。"""

    def __init__(self, npc_pos=(0.0, 0.0)):
        self.npc_pos = npc_pos
        self.player_pos = (20.0, 0.0)
        self.time = 0.0

    def distance(self, entity: str) -> float:
        if entity == "player":
            return math.dist(self.player_pos, self.npc_pos)
        return float("inf")

    def has_line_of_sight(self, entity: str) -> bool:
        return self.distance(entity) <= 12.0


class NpcRuntime:
    def __init__(self, config: dict, project: dict, world: World):
        self.config = config
        self.world = world
        self.attributes = dict(config.get("attributes", {}))
        self.lock = CapabilityLock(timeout=project.get("lockTimeout", 5.0))
        self.bus = EventBus()
        self.layer_order = list(project["layers"])
        self.time = 0.0

        self.layers = {}
        for layer_id in self.layer_order:
            layer_config = config.get("layers", {}).get(layer_id)
            if layer_config:
                self.layers[layer_id] = LayerMachine(layer_id, layer_config, self.lock, self.bus)

    def context(self, layer) -> dict:
        context = {
            "self": SimpleNamespace(**self.attributes),
            "player": "player",
            "time_in_state": layer.time_in_state,
            "distance": self.world.distance,
            "hasLineOfSight": self.world.has_line_of_sight,
        }
        # 把当帧事件注入为 on_xxx 变量，供条件表达式读取
        for event in self.bus.snapshot():
            context[f"on_{event}"] = True
        return context

    def tick(self, dt: float) -> None:
        self.time += dt
        self.world.time += dt

        for layer_id in self.layer_order:
            layer = self.layers.get(layer_id)
            if not layer:
                continue
            self.bus.merge_pending()
            layer.tick(dt, self.time, self.context)

        self.bus.end_frame()

    def snapshot(self) -> dict:
        return {
            layer_id: {
                "state": layer.current.name,
                "id": layer.current.id,
                "time": round(layer.time_in_state, 2),
            }
            for layer_id, layer in self.layers.items()
        }

    def locks(self) -> dict:
        return self.lock.holders()
