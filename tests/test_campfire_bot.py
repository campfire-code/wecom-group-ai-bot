"""不访问网络：假大模型 + 手工构造的回调样例。
样例 XML 按上游 req_msg.py 解析的字段构造，不是真实群里的抓包（未核实与线上完全一致）。"""
import logging
import os
import re
import xml.etree.ElementTree as ET

import pytest
from wx_crypt import WXBizMsgCrypt, WxChannel_Wecom

from campfire_bot import logsafe
from campfire_bot.bot import DEFAULT_FALLBACK, LLM_FAIL_REPLY, Answerer, extract_question
from campfire_bot.kb import KnowledgeBase, split_markdown, tokenize
from campfire_bot.llm import LLMError
from campfire_bot.main import build_server
from campfire_bot.prompt import NOT_FOUND_MARKER, build_messages
from wecom_bot_svr import ReqMsg

HERE = os.path.dirname(__file__)
KB_DIR = os.path.join(os.path.dirname(HERE), "kb-example")
TOKEN, AES = "tok_unit_123", "a" * 43


def fixture(name):
    with open(os.path.join(HERE, "fixtures", name), encoding="utf-8") as f:
        return f.read()


def parse(name):
    return ReqMsg.create_msg(ET.fromstring(fixture(name)))


class FakeLLM:
    def __init__(self, reply="7 天内未使用可退款。", fail=False):
        self.reply, self.fail, self.calls = reply, fail, []

    def chat(self, messages):
        self.calls.append(messages)
        if self.fail:
            raise LLMError("boom")
        return self.reply


# ---- 知识库检索 ----
def test_tokenize_mixed():
    assert tokenize("退款 API v2") == ["api", "v2", "退款"]
    assert "退款" in tokenize("申请退款流程") and "款流" in tokenize("申请退款流程")


def test_split_keeps_heading_path():
    chunks = split_markdown("a.md", "# 退款\n\n## 流程\n点申请\n\n## 条件\n7天\n")
    assert [(c.heading, c.text) for c in chunks] == [("退款 > 流程", "点申请"), ("退款 > 条件", "7天")]


def test_search_ranks_relevant_first():
    kb = KnowledgeBase(KB_DIR)
    hits = kb.search("退款流程是什么", top_k=3)
    assert hits and hits[0][1].source == "退款政策.md" and "退款流程" in hits[0][1].heading
    assert kb.search("顺丰快递几天发货", top_k=1)[0][1].source == "发货说明.md"


def test_search_miss_and_empty_dir(tmp_path):
    assert KnowledgeBase(KB_DIR).search("zzzzqqq xxyy") == []
    assert KnowledgeBase(str(tmp_path)).search("退款") == []


def test_kb_reload_on_change(tmp_path):
    kb = KnowledgeBase(str(tmp_path))
    assert kb.search("保修") == []
    (tmp_path / "x.md").write_text("# 保修\n整机保修一年", encoding="utf-8")
    assert kb.search("保修")


# ---- 提示词 ----
def test_build_messages_contains_context_and_question():
    hits = KnowledgeBase(KB_DIR).search("退款", top_k=2)
    msgs = build_messages("退款多久到账", hits)
    assert msgs[0]["role"] == "system" and NOT_FOUND_MARKER in msgs[0]["content"]
    assert "退款政策.md" in msgs[1]["content"] and "【问题】\n退款多久到账" in msgs[1]["content"]


# ---- 消息解析 ----
def test_extract_question_strips_at():
    assert extract_question(parse("text_group.xml"), "答疑助手") == "退款需要多久到账？"


def test_extract_question_nontext_none():
    assert extract_question(parse("image_group.xml"), "答疑助手") is None


# ---- 答疑流程 ----
def test_answer_uses_llm_with_context():
    llm = FakeLLM()
    a = Answerer(KnowledgeBase(KB_DIR), llm)
    assert a.answer("退款多久到账") == "7 天内未使用可退款。"
    assert "退款政策.md" in llm.calls[0][1]["content"]


def test_answer_kb_miss_skips_llm():
    llm = FakeLLM()
    assert Answerer(KnowledgeBase(KB_DIR), llm, fallback="没有").answer("zzzzqqq") == "没有"
    assert llm.calls == []


def test_answer_marker_gives_fallback():
    a = Answerer(KnowledgeBase(KB_DIR), FakeLLM(reply=NOT_FOUND_MARKER))
    assert a.answer("退款") == DEFAULT_FALLBACK


def test_answer_llm_failure():
    assert Answerer(KnowledgeBase(KB_DIR), FakeLLM(fail=True)).answer("退款") == LLM_FAIL_REPLY


# ---- 日志脱敏 ----
def test_redact_filter(caplog):
    f = logsafe.RedactFilter([TOKEN, AES, "sk-secret-xyz"])
    rec = logging.LogRecord("x", logging.ERROR, "", 0,
                            "t=%s url=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=ABCD1234 Bearer sk-secret-xyz",
                            (TOKEN,), None)
    f.filter(rec)
    out = rec.getMessage()
    assert TOKEN not in out and "ABCD1234" not in out and "sk-secret-xyz" not in out


# ---- 端到端：加密回调 -> 解密 -> 答疑 -> 加密回包 ----
@pytest.fixture
def client(monkeypatch):
    env = dict(WX_BOT_TOKEN=TOKEN, WX_BOT_AES_KEY=AES, WX_BOT_NAME="答疑助手", LLM_BASE_URL="http://x.invalid/v1",
               LLM_API_KEY="sk-test", LLM_MODEL="m", KB_DIR=KB_DIR)
    server = build_server(env)
    fake = FakeLLM()
    # 把假大模型换进已构造好的 handler
    from campfire_bot import main as m
    ans = Answerer(KnowledgeBase(KB_DIR), fake)
    mh, eh = m.make_handlers(ans, "答疑助手")
    server.set_message_handler(mh)
    server.set_event_handler(eh)
    server._app.get("/cb")(server.handle_bot_call_get)
    server._app.post("/cb")(server.handle_bot_call_post)
    return server, server._app.test_client(), fake


def encrypt_post(client, xml_name):
    c = WXBizMsgCrypt(TOKEN, AES, "", channel=WxChannel_Wecom)
    ret, body = c.EncryptMsg(fixture(xml_name).encode(), "n1", "1700000000")
    assert ret == 0
    sig = re.search(r"<MsgSignature><!\[CDATA\[(.*?)\]", body).group(1)
    r = client.post(f"/cb?msg_signature={sig}&timestamp=1700000000&nonce=n1", data=body.encode())
    reply = r.data
    sig2, ts2, n2 = (re.search(p, reply.decode()).group(1) for p in
                     [r"<MsgSignature><!\[CDATA\[(.*?)\]", r"<TimeStamp>(.*?)<", r"<Nonce><!\[CDATA\[(.*?)\]"])
    ret, plain = c.DecryptMsg(reply, sig2, ts2, n2)
    assert ret == 0
    return ET.fromstring(plain).find("Text/Content").text  # 上游回包为 ASCII 字符引用，需解析后比较


def test_healthz(client):
    assert client[1].get("/healthz").data == b"ok"


def test_callback_text_roundtrip(client):
    _, c, fake = client
    plain = encrypt_post(c, "text_group.xml")
    assert plain == "7 天内未使用可退款。"
    assert "退款需要多久到账？" in fake.calls[0][1]["content"]


def test_callback_url_verify(client):
    _, c, _ = client
    cr = WXBizMsgCrypt(TOKEN, AES, "", channel=WxChannel_Wecom)
    ret, enc = cr.EncryptMsg(b"echo-ok-123", "n1", "1700000000")
    g = lambda p: re.search(p, enc).group(1)
    r = c.get("/cb", query_string={"msg_signature": g(r"<MsgSignature><!\[CDATA\[(.*?)\]"), "timestamp": "1700000000",
                                   "nonce": "n1", "echostr": g(r"<Encrypt><!\[CDATA\[(.*?)\]")})
    assert r.data == b"echo-ok-123"


def test_callback_event_and_image(client):
    _, c, fake = client
    assert "答疑助手" in encrypt_post(c, "event_add.xml")
    assert "只支持文字" in encrypt_post(c, "image_group.xml")
    assert fake.calls == []
