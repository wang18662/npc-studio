"""控制台演示（C8）：模拟玩家靠近再离开，观察 NPC 三层状态流转。

用法（在项目根目录执行）：
    python tools/demo_console.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config_loader import ConfigLoader  # noqa: E402
from runtime.npc_runtime import NpcRuntime, World  # noqa: E402


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def distance_at(t: float, keys: list) -> float:
    for (t0, d0), (t1, d1) in zip(keys, keys[1:]):
        if t0 <= t <= t1:
            ratio = (t - t0) / (t1 - t0) if t1 > t0 else 0.0
            return lerp(d0, d1, ratio)
    return keys[-1][1]


def main() -> None:
    loader = ConfigLoader(ROOT)
    config = loader.load("guard_base")
    project = loader.project

    world = World()
    npc = NpcRuntime(config, project, world)

    # 时间线：0-2 远处 → 2s 玩家交互 → 2-6 对话中（玩家持续靠近）→ 6-11 停留 → 11-16 退回 → 16-22 远处
    keys = [(0.0, 20.0), (2.0, 20.0), (6.0, 1.0), (11.0, 1.0), (16.0, 20.0), (22.0, 20.0)]

    dt = 0.1
    duration = 22.0
    t = 0.0
    last_view = None
    talk_start, talk_end = 2.0, 6.0
    talk_sent = end_sent = False

    print("=" * 76)
    print("NPC Studio · 控制台演示")
    print("=" * 76)

    while t <= duration + 1e-9:
        world.player_pos = (distance_at(t, keys), 0.0)

        if not talk_sent and t >= talk_start:
            npc.bus.emit("player_interact")
            talk_sent = True
        if not end_sent and t >= talk_end:
            npc.bus.emit("dialogue_end")
            end_sent = True

        npc.tick(dt)

        snapshot = npc.snapshot()
        view = {lid: v["state"] for lid, v in snapshot.items()}

        if view != last_view:
            line = "  ".join(f"{lid[:4]}:{state}" for lid, state in view.items())
            print(f"[{t:5.1f}s] {line:<40} 距离 {world.distance('player'):4.1f}")
            last_view = view

        t += dt

    print()
    print("-" * 76)
    print("状态转移日志")
    print("-" * 76)
    for layer_id in npc.layer_order:
        layer = npc.layers.get(layer_id)
        if not layer:
            continue
        for log in layer.transitions_log:
            emit = f"   emit={log['emit']}" if log["emit"] else ""
            print(f"[{log['time']:5.1f}s] {log['layer']:<11} {log['from']} -> {log['to']}{emit}")

    print()
    print("-" * 76)
    print("能力锁持有情况")
    print("-" * 76)
    for cap, owner in sorted(npc.locks().items()):
        print(f"  {cap:<10} <- {owner}")

    if npc.lock.warnings:
        print()
        print("告警：")
        for warning in npc.lock.warnings:
            print(f"  {warning}")


if __name__ == "__main__":
    main()
