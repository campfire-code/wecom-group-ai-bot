"""入口：读环境变量，起上游 WecomBotServer，挂上答疑 handler。"""
import logging
import os
import sys

from wecom_bot_svr import RspTextMsg, WecomBotServer

from . import logsafe
from .bot import Answerer, NON_TEXT_REPLY, extract_question
from .kb import KnowledgeBase
from .llm import LLMClient

log = logging.getLogger("campfire_bot")
SECRET_ENVS = ("WX_BOT_TOKEN", "WX_BOT_AES_KEY", "WX_BOT_KEY", "LLM_API_KEY")


def text_rsp(content):
    r = RspTextMsg()
    r.content = content
    return r


def make_handlers(answerer, bot_name):
    def message_handler(req_msg):
        q = extract_question(req_msg, bot_name)
        if q is None:
            return text_rsp(NON_TEXT_REPLY)
        log.info("question chars=%d", len(q))  # 只记长度，不记提问内容
        return text_rsp(answerer.answer(q))

    def event_handler(req_msg):
        if getattr(req_msg, "event_type", "") == "add_to_chat":
            return text_rsp("大家好，我是答疑助手，@我 并提出问题即可。")
        return text_rsp("")

    return message_handler, event_handler


def build_server(env=os.environ):
    for k in ("WX_BOT_TOKEN", "WX_BOT_AES_KEY", "WX_BOT_NAME", "LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL"):
        if not env.get(k):
            raise SystemExit(f"缺少环境变量 {k}")
    kb = KnowledgeBase(env.get("KB_DIR", "/data/kb"))
    llm = LLMClient(env["LLM_BASE_URL"], env["LLM_API_KEY"], env["LLM_MODEL"])
    answerer = Answerer(
        kb, llm,
        fallback=env.get("KB_FALLBACK_REPLY", ""),
        top_k=int(env.get("KB_TOP_K", "4")),
        max_reply_chars=int(env.get("MAX_REPLY_CHARS", "1500")),
    )
    bot_name = env["WX_BOT_NAME"]
    server = WecomBotServer(
        bot_name, "0.0.0.0", int(env.get("PORT", "5001")),
        path=env.get("CALLBACK_PATH", "/wecom_bot"),
        token=env["WX_BOT_TOKEN"], aes_key=env["WX_BOT_AES_KEY"],
        corp_id=env.get("WX_BOT_CORP_ID", ""), bot_key=env.get("WX_BOT_KEY") or None,
    )
    mh, eh = make_handlers(answerer, bot_name)
    server.set_message_handler(mh)
    server.set_event_handler(eh)
    server._app.get("/healthz")(lambda: ("ok", 200))
    return server


def main():
    logging.basicConfig(stream=sys.stdout, level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logsafe.install([os.environ.get(k, "") for k in SECRET_ENVS])
    server = build_server()
    if not os.environ.get("WX_BOT_KEY"):
        log.warning("未设置 WX_BOT_KEY：大模型超过约 4 秒才答完时，无法主动推送回复")
    server.run()


if __name__ == "__main__":
    main()
