"""Ollama LLM 封装 — 绕过 langchain-ollama 解析 bug，支持依赖注入"""

import os
import threading

# 确保 localhost Ollama 连接不走系统代理（兼容 Clash/V2Ray 等软件开启系统代理的场景）
_no_proxy = os.environ.get("NO_PROXY", os.environ.get("no_proxy", ""))
if "localhost" not in _no_proxy:
    _combined = ",".join(filter(None, [_no_proxy, "localhost", "127.0.0.1"]))
    os.environ["NO_PROXY"] = _combined
    os.environ["no_proxy"] = _combined

from typing import Any, Iterator, Optional, Sequence

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field, PrivateAttr

from logger import get_logger


class OllamaLLMError(Exception):
    """Ollama 调用失败，调用方应据此决定降级策略"""
    def __init__(self, message: str, original_error: Exception | None = None):
        super().__init__(message)
        self.original_error = original_error

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sanitize_text(text):
    """移除 surrogate 字符 (U+D800–U+DFFF)，防止 UTF-8 编码失败"""
    if not text:
        return ""
    if isinstance(text, str):
        return "".join(ch for ch in text if not (0xD800 <= ord(ch) <= 0xDFFF))
    return str(text)


sanitize_text = _sanitize_text

_THINKING_MODELS = ("qwen3", "qwq", "deepseek-r1")


def _supports_thinking(model_name: str) -> bool:
    """判断模型是否支持 think 参数（Qwen3/QwQ/DeepSeek-R1 等 reasoning 模型）"""
    m = model_name.lower()
    return any(t in m for t in _THINKING_MODELS)


# ---------------------------------------------------------------------------
# OllamaChatModel
# ---------------------------------------------------------------------------

class OllamaChatModel(BaseChatModel):
    """直接封装 ollama 库的 LangChain ChatModel"""

    model: str = Field(default="qwen3.5:4b")
    base_url: str = Field(default="http://localhost:11434")
    temperature: float = Field(default=0.1)
    num_predict: int = Field(default=4096)
    _client: Any = PrivateAttr(default=None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        import ollama as _ollama

        self._client = _ollama.Client(host=self.base_url)

    def _convert_messages(self, messages: Sequence[BaseMessage]) -> list[dict]:
        converted = []
        for msg in messages:
            if isinstance(msg, SystemMessage):
                converted.append({"role": "system", "content": msg.content})
            elif isinstance(msg, HumanMessage):
                converted.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                converted.append({"role": "assistant", "content": msg.content})
            else:
                converted.append({"role": "user", "content": str(msg.content)})
        return converted

    def _generate(
        self,
        messages: Sequence[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs,
    ) -> ChatResult:
        ollama_messages = self._convert_messages(messages)
        options = {"temperature": self.temperature, "num_predict": self.num_predict}
        if stop:
            options["stop"] = stop
        try:
            chat_kwargs = dict(model=self.model, messages=ollama_messages, options=options)
            if _supports_thinking(self.model):
                chat_kwargs["think"] = False
            response = self._client.chat(**chat_kwargs)
            content = _sanitize_text(response.message.content or "")
        except Exception as e:
            raise OllamaLLMError(
                f"Ollama 调用失败 (model={self.model}): {e}", original_error=e,
            )

        message = AIMessage(content=content)
        return ChatResult(generations=[ChatGeneration(message=message)])

    def _stream(
        self,
        messages: Sequence[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs,
    ) -> Iterator[ChatGeneration]:
        ollama_messages = self._convert_messages(messages)
        options = {"temperature": self.temperature, "num_predict": self.num_predict}
        if stop:
            options["stop"] = stop
        try:
            chat_kwargs = dict(model=self.model, messages=ollama_messages, options=options, stream=True)
            if _supports_thinking(self.model):
                chat_kwargs["think"] = False
            stream = self._client.chat(**chat_kwargs)
            for chunk in stream:
                delta = chunk.get("message", {}).get("content", "")
                if delta:
                    yield ChatGeneration(message=AIMessage(content=_sanitize_text(delta)))
        except Exception as e:
            raise OllamaLLMError(
                f"Ollama 流式调用失败 (model={self.model}): {e}", original_error=e,
            )

    @property
    def _llm_type(self) -> str:
        return "ollama-chat"

    @property
    def _identifying_params(self) -> dict:
        return {"model": self.model, "temperature": self.temperature}


# ---------------------------------------------------------------------------
# Factory (支持 DI 覆盖)
# ---------------------------------------------------------------------------

_llm_instance = None
_llm_lock = threading.Lock()


def get_llm(model=None, base_url=None, temperature=0.1, force_new=False):
    """返回 OllamaChatModel 实例，支持依赖注入覆盖（双重检查锁定，线程安全）"""
    global _llm_instance
    if model or base_url or force_new:
        import config
        return OllamaChatModel(
            model=model or config.LLM_MODEL,
            base_url=base_url or config.OLLAMA_BASE_URL,
            temperature=temperature,
            num_predict=4096,
        )
    if _llm_instance is None:
        with _llm_lock:
            if _llm_instance is None:
                import config
                _llm_instance = OllamaChatModel(
                    model=config.LLM_MODEL,
                    base_url=config.OLLAMA_BASE_URL,
                    temperature=temperature,
                    num_predict=4096,
                )
    return _llm_instance
