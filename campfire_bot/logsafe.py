"""日志脱敏：把 token / aes_key / api key / webhook key 的值替换成 ***。"""
import logging
import re

_URL_KEY = re.compile(r"([?&]key=)[^&\s'\"]+")
_BEARER = re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]+")


class RedactFilter(logging.Filter):
    def __init__(self, secrets):
        super().__init__()
        self.secrets = [s for s in secrets if s and len(s) >= 3]

    def redact(self, text):
        for s in self.secrets:
            text = text.replace(s, "***")
        text = _URL_KEY.sub(r"\1***", text)
        return _BEARER.sub(r"\1***", text)

    def filter(self, record):
        try:
            msg = record.getMessage()
        except Exception:
            msg = str(record.msg)
        record.msg = self.redact(msg)
        record.args = None
        if record.exc_info:  # 异常堆栈里也可能带 URL，提前格式化并脱敏
            record.exc_text = self.redact(logging.Formatter().formatException(record.exc_info))
            record.exc_info = None
        return True


def install(secrets):
    """给根日志的所有 handler 加过滤器（在 basicConfig 之后调用）。"""
    f = RedactFilter(secrets)
    for h in logging.getLogger().handlers:
        h.addFilter(f)
    return f
