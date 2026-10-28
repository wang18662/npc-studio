"""命令行校验工具。

用法（在项目根目录执行）：
    python tools/validate.py                 # 校验 npcs/ 下所有文件
    python tools/validate.py elite_guard     # 校验指定 NPC
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from validator import Validator  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    validator = Validator(ROOT)

    if len(sys.argv) > 1:
        targets = sys.argv[1:]
    else:
        targets = sorted(p.stem for p in (ROOT / "npcs").glob("*.json"))

    if not targets:
        print("npcs/ 下没有找到配置文件")
        return 1

    failed = 0
    for npc_id in targets:
        report = validator.validate(npc_id)
        status = "通过" if report.ok else f"{len(report.errors)} 个错误"
        print(f"[{npc_id}] {status}")
        for issue in report.issues:
            print(f"  {issue}")
        if not report.ok:
            failed += 1
        print()

    print(f"合计 {len(targets)} 个，失败 {failed} 个")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
