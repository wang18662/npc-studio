"""轻量知识库检索（E3 的简化实现）。

用「中文字 + 英文词」的重叠度打分，替代向量检索。
好处是零依赖、可解释；后续要换成 BGE/FAISS，只需替换 search 的实现。
"""

import math
import re
from pathlib import Path


class KnowledgeBase:
    def __init__(self, root: Path, name: str):
        self.sections = []
        self.idf = {}
        self._load(Path(root), name)

    def _load(self, root: Path, name: str) -> None:
        path = root / "dialogues" / "knowledge" / f"{name}.md"
        if not path.exists():
            return

        text = path.read_text(encoding="utf-8")
        blocks = re.split(r"^##\s+", text, flags=re.M)

        for block in blocks[1:]:
            lines = block.strip().splitlines()
            if not lines:
                continue
            title = lines[0].strip()
            body = "\n".join(lines[1:]).strip()
            if not body:
                continue
            self.sections.append(
                {
                    "id": title,
                    "title": title,
                    "text": body,
                    "tokens": self._tokens(body),
                }
            )

        self._build_idf()

    def _build_idf(self) -> None:
        """字符级 IDF：出现越少见的字，区分度越高。"""
        if not self.sections:
            self.idf = {}
            return

        doc_freq = {}
        for section in self.sections:
            for token in section["tokens"]:
                doc_freq[token] = doc_freq.get(token, 0) + 1

        total = len(self.sections)
        self.idf = {
            token: math.log((total + 1) / (freq + 0.5)) for token, freq in doc_freq.items()
        }

    @staticmethod
    def _tokens(text: str) -> set:
        chars = set(re.findall(r"[\u4e00-\u9fff]", text))
        words = set(re.findall(r"[a-zA-Z]+", text.lower()))
        return chars | words

    def search(self, query: str, refs: list = None, top_k: int = 2) -> list:
        """检索知识片段。

        - 有 refs 且能匹配到小节：直接返回这些小节（配置即权威，不靠算法猜）
        - 无 refs：按 IDF 加权做字面检索
        """
        if refs:
            matched = [s for s in self.sections if s["id"] in refs]
            if matched:
                return matched[:top_k]

        query_tokens = self._tokens(query)
        if not query_tokens:
            return []

        scored = []
        for section in self.sections:
            title_tokens = self._tokens(section["title"])
            score = 0.0
            for token in query_tokens:
                weight = self.idf.get(token, 0.1)
                if token in section["tokens"]:
                    score += weight
                if token in title_tokens:
                    score += weight * 2
            if score > 0:
                scored.append((score, section))

        scored.sort(key=lambda item: -item[0])
        return [section for _, section in scored[:top_k]]

    def titles(self) -> list:
        return [s["id"] for s in self.sections]
