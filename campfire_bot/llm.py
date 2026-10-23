"""兼容 OpenAI 的 chat/completions 调用。密钥只放请求头，不写日志。"""
import requests


class LLMError(Exception):
    pass


class LLMClient:
    def __init__(self, base_url, api_key, model, timeout=60):
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def chat(self, messages):
        try:
            r = requests.post(
                self.url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.model, "messages": messages, "temperature": 0.2},
                timeout=self.timeout,
            )
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"].strip()
        except (requests.RequestException, KeyError, IndexError, ValueError) as e:
            # 只记录异常类型和状态码，不记录请求头与响应体
            status = getattr(getattr(e, "response", None), "status_code", None)
            raise LLMError(f"{type(e).__name__} status={status}") from None
