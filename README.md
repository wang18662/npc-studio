# NPC Studio

面向策划的 AI NPC 行为与对话配置工具。让策划不写代码，就能设计 NPC 的状态、行为与对话，并把配置直接驱动到游戏里运行。

---

## 一、环境要求

| 项 | 要求 |
|---|---|
| Python | 3.10 及以上 |
| 依赖 | 运行时零依赖；**校验功能**需要 `jsonschema` |
| 浏览器 | Chrome / Edge 等现代浏览器 |

如果报「未安装 jsonschema」：

```bash
pip install jsonschema
```

> Anaconda 自带的 Python 通常已经装了 jsonschema，可直接用。

---

## 二、启动（推荐：浏览器演示）

```bash
cd C:\Users\25544\Desktop\npc-studio
python server/server.py
```

看到这行说明启动成功：

```
NPC Studio 演示已启动：http://127.0.0.1:8765
```

然后打开两个页面：

| 地址 | 用途 |
|---|---|
| http://127.0.0.1:8765 | **运行时演示**：操作玩家，观察 NPC 三层状态 |
| http://127.0.0.1:8765/editor | **配置编辑器**：改配置、看 JSON、保存、导出 |

停止服务：在终端按 `Ctrl+C`。

---

## 三、演示页怎么玩

| 操作 | 效果 |
|---|---|
| `WASD` / 方向键 | 移动玩家（红点） |
| 靠近 NPC 到 **8 米内** | NPC 进入追击 |
| 靠近到 **2 米内** | 移动层驻留 + 战斗层攻击 |
| `E` 键 | 开始 / 结束对话 |
| 右侧输入框 | 打字跟 NPC 说话，回车发送 |

右侧面板实时显示：三层状态、能力锁、转移历史、本帧事件。

Canvas 上的两个圈：**虚线大圈 = 视野 8m**，**细红圈 = 攻击范围 2m**。

---

## 四、编辑器怎么用

1. 左侧点击任意状态（如「巡逻」）
2. 中间改字段：名称、原型、优先级、需要能力、锁定能力、参数
3. 右侧 JSON 实时变化
4. 点「保存」→ 自动跑 15 条校验规则
5. 校验通过才写入文件；有错误会列出规则编号和出错位置

**注意**：保存后需要重启服务器，运行时才会用新配置。

导出按钮：

| 按钮 | 产出 |
|---|---|
| 导出 DataTable | CSV，可直接导入 UE |
| 导出文档 | Markdown 配置手册 |

---

## 五、命令行工具

```bash
# 校验所有 NPC 配置（15 条规则）
python tools/validate.py

# 校验单个
python tools/validate.py elite_guard

# 查看继承解析结果（父子覆盖对比）
python tools/load_npc.py elite_guard

# 纯终端演示，不需要浏览器
python tools/demo_console.py
```

测试脚本（开发用）：

```bash
python tools/test_inheritance.py   # 继承：循环、超深、无效路径
python tools/test_validator.py     # 校验：15 个规则用例
python tools/test_tools.py         # 工具：六步校验链
```

---

## 六、目录结构

```
npc-studio/
├── project.json              # 项目配置：能力表、层定义、参数定义
├── npcs/
│   ├── guard_base.json       # 基础 NPC（9 个状态）
│   └── elite_guard.json      # 精英守卫（继承 guard_base）
├── schema/
│   └── npc.schema.json       # 配置的 JSON Schema
├── dialogues/
│   └── knowledge/
│       └── guard_faq.md      # 守卫知识库（6 个知识小节）
├── runtime/                  # 运行时内核
│   ├── state.py              # 状态定义 + 条件表达式求值
│   ├── layer_machine.py      # 单层状态机
│   ├── capability_lock.py    # 能力锁 + 优先级抢占
│   ├── event_bus.py          # 跨层事件
│   ├── behavior_tree.py      # 行为树执行器
│   ├── npc_runtime.py        # 三层并行调度
│   ├── ai_gateway.py         # 意图识别 + 生成 + 工具申请
│   ├── tool_executor.py      # 八件工具 + 六步校验
│   └── knowledge.py          # 轻量 RAG（IDF 检索）
├── server/
│   ├── server.py             # 零依赖 HTTP 服务
│   └── static/               # 演示页 + 编辑器页
└── tools/                    # 命令行工具与测试
```

---

## 七、改配置的完整流程

```
① 打开 /editor
② 改字段（右侧立刻看到 JSON 变化）
③ 点保存 → 校验通过才落盘
④ 重启 server
⑤ 回到 / 观察行为变化
```

这就是「配置驱动」的闭环：**改数据，不改代码**。

---

## 八、AI 模式

默认是 `mock` 模式：规则生成回复，**零依赖、零成本**，用于本地演示。

想接真实大模型：

1. 设置环境变量

```bash
set DEEPSEEK_API_KEY=你的key        # Windows CMD
$env:DEEPSEEK_API_KEY="你的key"     # PowerShell
```

2. 修改 `project.json` 对应 NPC 的 ai 配置（或在 `npcs/guard_base.json` 里）：

```json
"ai": { "mode": "deepseek", "model": "deepseek-chat" }
```

3. 重启服务器

---

## 九、常见问题

**端口被占用**

```
OSError: [WinError 10048] 通常每个套接字地址只允许使用一次
```

改 `server/server.py` 顶部的 `PORT`（默认 8765）。

**页面打不开**

确认终端里打印了「演示已启动」，且浏览器地址是 `http://127.0.0.1:8765`（不是 https）。

**改了配置但行为没变**

保存后需要**重启服务器**，因为运行时在启动时加载配置。

**校验报「未安装 jsonschema」**

```bash
pip install jsonschema
```

---

## 十、核心设计

- **分层并行状态机**：移动层 / 交互层 / 战斗层同时运行，用事件通信
- **能力锁**：层间冲突用「锁住能力」仲裁；高优先级可抢占
- **AI 只有申请权**：Function Calling 必须经过六步校验才能执行
- **Schema 管形状，不管内容**：换项目只需换数据，不改结构

---

## 十一、设计文档

位于 `C:\Users\25544\WorkBuddy\岗位JD\`：

| 文档 | 内容 |
|---|---|
| `NPC-Studio-项目介绍.md` | 项目是什么、为谁做、架构与决策 |
| `NPC-Studio-配置规范.md` | 完整字段定义与 15 条校验规则 |
| `design-doc.md` | 设计取舍与代价 |
| `NPC-Studio-实施步骤.md` | 分阶段实施计划 |
