"""本地 Markdown 知识库：切段 + 关键词检索（纯标准库，无外部依赖）。"""
import math
import os
import re
from dataclasses import dataclass

_WORD = re.compile(r"[a-z0-9_]+")
_CJK = re.compile(r"[一-鿿]+")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
MAX_CHUNK_CHARS = 600


@dataclass
class Chunk:
    source: str   # 相对知识库目录的文件路径
    heading: str  # 所在标题路径，如 "退款 > 流程"
    text: str


def tokenize(text):
    """英文数字按词，中文按相邻两字（单个汉字只在整段仅一个字时保留）。"""
    text = text.lower()
    tokens = _WORD.findall(text)
    for run in _CJK.findall(text):
        if len(run) == 1:
            tokens.append(run)
        else:
            tokens.extend(run[i:i + 2] for i in range(len(run) - 1))
    return tokens


def split_markdown(source, content):
    """按标题分节，节内按空行分段，段落累加到不超过 MAX_CHUNK_CHARS。"""
    chunks, stack, buf = [], [], []

    def flush():
        para = "\n".join(buf).strip()
        buf.clear()
        if para:
            chunks.append(Chunk(source, " > ".join(h for _, h in stack), para))

    def add_para(par):
        cur = "\n".join(buf)
        if cur and len(cur) + len(par) > MAX_CHUNK_CHARS:
            flush()
        buf.append(par)
        while len("\n".join(buf)) > MAX_CHUNK_CHARS * 2:  # 超长单段硬切
            joined = "\n".join(buf)
            buf[:] = [joined[:MAX_CHUNK_CHARS]]
            flush()
            buf.append(joined[MAX_CHUNK_CHARS:])

    para_lines = []
    in_code = False

    def end_para():
        if para_lines:
            add_para("\n".join(para_lines))
            para_lines.clear()

    for line in content.splitlines():
        if line.strip().startswith("```"):
            in_code = not in_code
        m = None if in_code else _HEADING.match(line)
        if m:
            end_para()
            flush()
            level = len(m.group(1))
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, m.group(2).strip()))
        elif not in_code and not line.strip():
            end_para()
        else:
            para_lines.append(line)
    end_para()
    flush()
    return chunks


class KnowledgeBase:
    def __init__(self, directory):
        self.directory = directory
        self._sig = None
        self._chunks = []
        self._df = {}
        self._tok = []

    def _signature(self):
        sig = []
        for root, _, files in os.walk(self.directory):
            for f in files:
                if f.lower().endswith((".md", ".markdown")):
                    p = os.path.join(root, f)
                    try:
                        sig.append((p, os.stat(p).st_mtime_ns))
                    except OSError:
                        pass
        return sorted(sig)

    def _reload_if_changed(self):
        sig = self._signature()
        if sig == self._sig:
            return
        chunks = []
        for path, _ in sig:
            try:
                with open(path, encoding="utf-8") as fh:
                    content = fh.read()
            except (OSError, UnicodeDecodeError):
                continue
            chunks.extend(split_markdown(os.path.relpath(path, self.directory), content))
        self._chunks = chunks
        self._tok = [set(tokenize(c.heading + "\n" + c.text)) for c in chunks]
        df = {}
        for toks in self._tok:
            for t in toks:
                df[t] = df.get(t, 0) + 1
        self._df = df
        self._sig = sig

    def search(self, query, top_k=4, min_score=0.0):
        """返回 [(分数, Chunk)]，按分数降序。分数 = 命中词的 IDF 之和（标题命中加权）。"""
        self._reload_if_changed()
        q = set(tokenize(query))
        n = len(self._chunks)
        if not q or n == 0:
            return []
        scored = []
        for chunk, toks in zip(self._chunks, self._tok):
            score = 0.0
            head = set(tokenize(chunk.heading))
            for t in q & toks:
                w = math.log(1 + n / self._df[t])
                score += w * (1.5 if t in head else 1.0)
            if score > min_score:
                scored.append((score, chunk))
        scored.sort(key=lambda x: -x[0])
        return scored[:top_k]
