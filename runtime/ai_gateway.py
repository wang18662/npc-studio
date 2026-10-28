"""AI 网关（E1 / E2 / E4）：意图识别 → 知识检索 → 生成 → 工具申请。

两种模式：
- mock（默认）：规则生成，零依赖、零成本，用于本地演示
- deepseek：调用真实 API，需要环境变量 DEEPSEEK_API_KEY

设计原则：LLM 只有「申请权」，工具是否执行由 ToolExecutor 的六步校验决定。
"""

import json
import os
import re
import urllib.request


class AIGateway:
    TOOL_KEYWORDS = {
        "give_quest": ["任务", "帮忙", "做什么", "需要我"],
        "open_door": ["开门", "放我进", "打开门"],
        "trade": ["买", "卖", "交易", "多少钱"],
        "give_item": ["给我", "物品"],
        "summon_ally": ["援军", "叫人", "帮忙打", "召唤"],
        "heal": ["治疗", "回血", "受伤"],
        "apply_buff": ["增益", "加状态"],
        "flee": ["撤退", "快跑"],
    }

    def __init__(self, ai_config: dict, knowledge, tool_executor, mode: str = None):
        self.config = ai_config or {}
        self.knowledge = knowledge
        self.tools = tool_executor
        self.mode = mode or self.config.get("mode", "mock")
        self.intents = self.config.get("intents", [])
        self.tool_configs = {
            t["name"]: t for t in self.config.get("tools", []) if t.get("enabled")
        }
        self.api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        self.model = self.config.get("model", "deepseek-chat")

    # ---------- E2 意图识别 ----------

    def _match_intent(self, message: str):
        best = None
        best_score = 0.0
        for intent in self.intents:
            score = max(
                (self._similarity(message, example) for example in intent.get("examples", [])),
                default=0.0,
            )
            if score > best_score:
                best_score = score
                best = intent
        return best if best_score >= 0.25 else None

    @staticmethod
    def _similarity(a: str, b: str) -> float:
        tokens_a = set(re.findall(r"[\u4e00-\u9fff]|[a-zA-Z]+", a.lower()))
        tokens_b = set(re.findall(r"[\u4e00-\u9fff]|[a-zA-Z]+", b.lower()))
        if not tokens_a or not tokens_b:
            return 0.0
        return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)

    # ---------- 工具触发判断 ----------

    def _should_call(self, tool_name: str, message: str) -> bool:
        return any(keyword in message for keyword in self.TOOL_KEYWORDS.get(tool_name, []))

    # ---------- 主流程 ----------

    def chat(self, message: str, ctx: dict) -> dict:
        intent = self._match_intent(message)

        # 没有识别到意图就不检索，直接走兜底——避免字面巧合召回无关内容
        snippets = (
            self.knowledge.search(message, intent.get("knowledgeRefs")) if intent else []
        )
        reply = self._generate(message, intent, snippets)

        tool_result = None
        if intent:
            for tool_name in intent.get("allowedTools", []):
                if tool_name not in self.tool_configs:
                    continue
                if not self._should_call(tool_name, message):
                    continue

                call_ctx = dict(ctx)
                call_ctx["allowed_tools"] = intent.get("allowedTools", [])
                call_ctx["owner"] = ctx.get("owner")
                tool_result = self.tools.request(
                    tool_name, {}, self.tool_configs[tool_name], call_ctx
                )
                break

        return {
            "reply": reply,
            "intent": intent["id"] if intent else None,
            "intentName": intent["name"] if intent else None,
            "snippets": [s["id"] for s in snippets],
            "tool": tool_result,
            "mode": self.mode,
        }

    # ---------- E4 生成（含兜底） ----------

    def _generate(self, message: str, intent, snippets) -> str:
        if self.mode == "deepseek" and self.api_key:
            try:
                return self._call_deepseek(message, intent, snippets)
            except Exception as err:  # noqa: BLE001
                fallback = intent.get("fallback") if intent else "……"
                return f"{fallback}（模型暂时不可用：{err}）"

        if snippets:
            return snippets[0]["text"]

        if intent:
            return intent.get("fallback", "……")

        return "……（他看了你一眼，没有说话。）"

    def _call_deepseek(self, message: str, intent, snippets) -> str:
        system = "你是一个中世纪风格的守卫 NPC，用简短自然的中文回答，不超过两句话。"
        if snippets:
            system += "\n只能依据以下信息回答：\n" + "\n".join(s["text"] for s in snippets)

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": message},
            ],
            "temperature": self.config.get("temperature", 0.7),
            "max_tokens": 120,
        }

        request = urllib.request.Request(
            "https://api.deepseek.com/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"].strip()
