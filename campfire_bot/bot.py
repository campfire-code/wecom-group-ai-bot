"""消息解析与答疑流程（与网络、Flask 解耦，便于单测）。"""
import logging
import re

from .prompt import NOT_FOUND_MARKER, build_messages

log = logging.getLogger("campfire_bot")

DEFAULT_FALLBACK = "抱歉，知识库里暂时没有这个问题的答案，请联系管理员补充或直接咨询负责人。"
LLM_FAIL_REPLY = "抱歉，答疑服务暂时不可用，请稍后再试。"
NON_TEXT_REPLY = "目前只支持文字提问。"


def extract_question(req_msg, bot_name=""):
    """从上游解析出的 ReqMsg 取出问题文本；非文本返回 None。
    去掉 @机器人名（上游已按名字去掉一次，这里再兜底，含全角空格/不间断空格）。"""
    if req_msg.msg_type == "text":
        raw = req_msg.content or ""
    elif req_msg.msg_type == "mixed":
        raw = " ".join(i.content for i in req_msg.msg_items if i.msg_type == "text" and i.content)
    else:
        return None
    if bot_name:
        raw = raw.replace(f"@{bot_name}", " ")
    raw = raw.replace(" ", " ").replace(" ", " ").replace("　", " ")
    return re.sub(r"\s+", " ", raw).strip()


class Answerer:
    def __init__(self, kb, llm, fallback=DEFAULT_FALLBACK, top_k=4, min_score=0.0, max_reply_chars=1500):
        self.kb, self.llm = kb, llm
        self.fallback = fallback or DEFAULT_FALLBACK
        self.top_k, self.min_score = top_k, min_score
        self.max_reply_chars = max_reply_chars

    def answer(self, question):
        if not question:
            return "请在 @我 后面写上你的问题。"
        hits = self.kb.search(question, self.top_k, self.min_score)
        if not hits:
            log.info("kb miss, skip llm")
            return self.fallback
        try:
            text = self.llm.chat(build_messages(question, hits))
        except Exception as e:
            log.warning("llm call failed: %s", e)
            return LLM_FAIL_REPLY
        if not text or NOT_FOUND_MARKER in text:
            return self.fallback
        if len(text) > self.max_reply_chars:
            text = text[: self.max_reply_chars] + "…"
        return text
