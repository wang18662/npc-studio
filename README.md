# NPC Studio

把 NPC 的 AI 参数从代码里抽出来，做成策划能改的配置。

**它只做一件事**：编辑一份参数表 → 导出 CSV → UE 导入 DataTable → 敌人行为按表变化。

不绑定引擎字段名，换项目只写一份映射配置。

---

## 一、环境要求

| 项 | 要求 |
|---|---|
| Python | 3.10 及以上 |
| 依赖 | **零依赖**，只用标准库 |
| 浏览器 | Chrome / Edge 等现代浏览器 |

---

## 二、启动

```bash
cd C:\Users\25544\Desktop\npc-studio
python server/server.py
```

看到这行就成功了：

```
NPC Studio 参数档案：http://127.0.0.1:8765/profiles
```

浏览器打开 **http://127.0.0.1:8765/profiles**（访问根路径会自动跳转）。

按 `Ctrl+C` 停止。

---

## 三、页面能做什么

### 1. 编辑参数

左侧选档案（`Guard_Grunt` / `Guard_Elite` / `Guard_Heavy`），右侧按分组显示 29 个参数。

- **标签右侧的蓝色徽标**（如 `C001 C004`）= 这个参数受哪几条约束限制，悬停看约束原文
- **悬停在字段上** = 看这个参数的说明（改大改小会怎样）

### 2. 约束校验

底部实时检查 9 条规则，例如：

> 停火距离应小于「边退边打距离」，否则血量低时反而贴得更近

**配错了不用等进游戏才发现。**

### 3. 对比

顶部「对比」下拉选另一个档案，下方列出差异：

| 参数 | Guard_Grunt | Guard_Elite | 差异 |
|---|---|---|---|
| 停火距离 | 250cm | 300cm | +50 |

「只看差异」开关控制是否隐藏相同的项。

### 4. 版本历史

每次点「保存」，系统自动把旧内容存一份：

- **相同内容只保留一份**（来回回滚不会堆重复）
- 最多保留 50 份，自动淘汰最旧的
- 点任意版本可以**回滚**，回滚前当前状态也会被备份

### 5. 导出

点「导出 CSV」下载，直接给 UE 的 DataTable 导入。

---

## 四、接到 UE 的完整流程

```
① 网页改参数 → 点保存（写回 profiles/ai_profiles.csv）
② 导出 CSV（或直接用那个文件）
③ UE 里右键 DT_NPCAIProfile → Reimport
④ Play，走近敌人看效果
```

**不用改代码、不用编译。**

字段怎么映射到 UE 的变量，写在 `adapters/shooterai.json` 里；UE 侧读这份配置用反射赋值。

---

## 五、目录结构

```
npc-studio/
├── schemas/
│   └── npc.pursue.json        # 参数定义（29 字段 + 9 条约束，通用语义键）
├── adapters/
│   └── shooterai.json         # 通用键 → UE 字段名映射（唯一出现引擎字段名的地方）
├── profiles/
│   ├── ai_profiles.csv        # 参数档案数据（也是 UE DataTable 的导入格式）
│   └── history/               # 版本快照（自动生成）
├── server/
│   ├── server.py              # 零依赖 HTTP 服务
│   └── static/
│       ├── profiles.html      # 参数档案页
│       ├── profiles.css
│       └── profiles.js        # Schema 驱动，不含任何硬编码字段
├── runtime/                   # 三层状态机实现（Python 参考实现，见第六节）
├── npcs/                      # 状态机配置（runtime 用）
└── tools/                     # 命令行工具与测试
```

---

## 六、关于 `runtime/` 和 `npcs/`

这两块是项目早期的「三层并行状态机 + 能力锁」实现，用来验证那套设计能不能跑。

**它和 ShooterAI 的实际 AI 无关**——那边用的是 UE 的 StateTree，没有三层并行，也没有能力锁。

命令行还能跑：

```bash
python tools/demo_console.py    # 纯终端跑一遍三层状态机
python tools/validate.py        # 校验 npcs/ 下的状态机配置
```

> **不要把它当成「游戏里敌人的行为预览」**——它不是。要看真实行为，只能进 UE。
>
> 网页侧的运行时演示页已于 2026-10-28 删除：它展示的状态与真实项目无关，会让人误以为改那里就能影响游戏。

---

## 七、命令行工具

```bash
# 检查 schema 与 adapter 是否对齐
python tools/check_schema.py

# 校验 npcs/ 下的状态机配置
python tools/validate.py

# 看继承解析结果
python tools/load_npc.py elite_guard
```

---

## 八、常见问题

**端口被占用**

改 `server/server.py` 顶部的 `PORT`（默认 8765）。

**改了参数但游戏没变**

流程少了一步：

```
网页保存 → CSV 变了
UE 里 Reimport → DataTable 变了
Play → 才生效
```

漏了 Reimport，DataTable 还是旧的。

**版本历史里看不到某个版本**

相同内容只存一份。两个版本内容完全一致时只会出现一次。

---

## 九、设计说明

### Schema 管形状，Adapter 管翻译

```
schema.json   定义「有哪些参数、什么类型、什么范围、什么约束」
              ↓ 通用语义键（如 pursue.stopDistance）
adapter.json  定义「这个键对应引擎里的哪个字段」
              ↓
UE 反射赋值   FindPropertyByName + CopyCompleteValue
```

**代码里不出现任何具体字段名**——换项目只改两份 JSON。

### 约束为什么放在 Schema 里

参数之间的隐性依赖（停火距离 < 边退边打距离）原本散落在代码注释里，策划看不到。

搬进 Schema 后：

- 网页实时校验
- 字段旁边显示它受哪几条约束限制
- 加新约束不用改前端

---

## 十、设计文档

位于 `C:\Users\25544\WorkBuddy\岗位JD\`：

| 文档 | 内容 |
|---|---|
| `NPC-Studio-通用化复盘.md` | 通用化改造的完整记录（含 5 个坑） |
| `NPC-Studio-通用化方案.md` | 三层架构设计与取舍 |
| `NPC-Studio-配置规范.md` | 状态机配置的字段定义（runtime 用） |
| `NPC-Studio-待做清单.md` | 已完成 / 待做 |
