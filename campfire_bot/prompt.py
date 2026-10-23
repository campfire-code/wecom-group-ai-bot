"""提示词组装。"""

SYSTEM_TEMPLATE = (
    "你是企业微信群里的答疑助手。只能根据下面【知识库资料】回答问题，不要使用资料以外的知识，不要编造。\n"
    "回答要简洁、口语化，使用中文。\n"
    "如果资料里没有足够信息回答该问题，只回复这一个标记，不要加其他文字：{marker}"
)
NOT_FOUND_MARKER = "[[NO_ANSWER]]"


def build_messages(question, hits):
    """hits: [(score, Chunk)]。返回 OpenAI chat messages。"""
    parts = []
    for i, (_, c) in enumerate(hits, 1):
        title = f"{c.source}" + (f" / {c.heading}" if c.heading else "")
        parts.append(f"[{i}] 来源：{title}\n{c.text}")
    context = "\n\n".join(parts) if parts else "（无）"
    return [
        {"role": "system", "content": SYSTEM_TEMPLATE.format(marker=NOT_FOUND_MARKER)},
        {"role": "user", "content": f"【知识库资料】\n{context}\n\n【问题】\n{question}"},
    ]
