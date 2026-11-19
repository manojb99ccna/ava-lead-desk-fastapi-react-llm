"""Local LLM, running inside the backend process (PyTorch + Hugging Face transformers).

No API key, no paid service and no separate server: the open-weight model files are downloaded
once into backend/llm_models/ and then everything runs offline.

The default model is Qwen2.5-Instruct (Apache-2.0), which supports tool calling through its chat
template: the model writes <tool_call>{"name": ..., "arguments": {...}}</tool_call> blocks.

Configuration (backend/.env):
    LLM_PROVIDER=local | none
    LLM_MODEL=Qwen/Qwen2.5-1.5B-Instruct     (any Hugging Face chat model with a tool-aware template)
    LLM_DEVICE=auto | cpu | cuda
    LLM_MAX_NEW_TOKENS, LLM_TIMEOUT_SECONDS, LLM_THREADS, LLM_TEMPERATURE

Other providers can be added later by implementing `LLMClient.complete`.
"""
import json
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Protocol

from ..core.config import settings

logger = logging.getLogger("ava.llm")


class LLMUnavailable(Exception):
    """The LLM could not produce an answer (not configured, still loading, busy, timeout, bad output)."""


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class LLMReply:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)

    def as_message(self) -> dict:
        """The assistant message to append to the history before sending tool results back."""
        message = {"role": "assistant", "content": self.content or ""}
        if self.tool_calls:
            message["tool_calls"] = [
                {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": c.arguments}}
                for c in self.tool_calls
            ]
        return message


class LLMClient(Protocol):
    def is_ready(self) -> bool: ...

    def complete(self, messages: list[dict], tools: list[dict]) -> LLMReply: ...


_TOOL_CALL_RE = re.compile(r"<tool_call>\s*(.*?)\s*(?:</tool_call>|$)", re.DOTALL)


def parse_model_output(text: str) -> LLMReply:
    """Splits generated text into plain content and <tool_call> blocks."""
    calls = []
    for i, raw in enumerate(_TOOL_CALL_RE.findall(text)):
        try:
            data = json.loads(raw)
        except ValueError:
            # Malformed call: the agent will report it back to the model as an error.
            calls.append(ToolCall(id=f"call_{i}", name="__invalid__", arguments={"raw": raw[:500]}))
            continue
        if not isinstance(data, dict) or not isinstance(data.get("name"), str):
            calls.append(ToolCall(id=f"call_{i}", name="__invalid__", arguments={"raw": raw[:500]}))
            continue
        args = data.get("arguments") or {}
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except ValueError:
                args = {}
        calls.append(ToolCall(id=f"call_{i}", name=data["name"], arguments=args if isinstance(args, dict) else {}))
    content = _TOOL_CALL_RE.sub("", text).strip()
    return LLMReply(content=content or None, tool_calls=calls)


class LocalTransformersClient:
    """Loads the model once (in a background thread) and serves one generation at a time."""

    def __init__(self, model_name: str, device: str, max_new_tokens: int, timeout: float,
                 temperature: float, threads: int, cache_dir: str | None):
        self.model_name = model_name
        self.device_setting = device
        self.max_new_tokens = max_new_tokens
        self.timeout = timeout
        self.temperature = temperature
        self.threads = threads
        self.cache_dir = cache_dir
        self._model = None
        self._tokenizer = None
        self._device = "cpu"
        self._error: str | None = None
        self._loading = False
        self._load_lock = threading.Lock()
        self._generate_lock = threading.Lock()

    # -- loading ---------------------------------------------------------
    def start_loading(self) -> None:
        with self._load_lock:
            if self._loading or self._model is not None:
                return
            self._loading = True
        threading.Thread(target=self._load, name="llm-loader", daemon=True).start()

    def _load(self) -> None:
        started = time.monotonic()
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer

            if self.threads > 0:
                torch.set_num_threads(self.threads)
            if self.device_setting == "auto":
                self._device = "cuda" if torch.cuda.is_available() else "cpu"
            else:
                self._device = self.device_setting
            # bfloat16 is emulated (very slow) on most CPUs, so CPU uses float32.
            dtype = torch.float16 if self._device == "cuda" else torch.float32

            logger.info("Loading local LLM %s on %s ...", self.model_name, self._device)
            tokenizer = AutoTokenizer.from_pretrained(self.model_name, cache_dir=self.cache_dir)
            model = AutoModelForCausalLM.from_pretrained(self.model_name, dtype=dtype, cache_dir=self.cache_dir)
            model.to(self._device)
            model.eval()
            self._tokenizer, self._model = tokenizer, model
            logger.info("Local LLM ready in %.1fs", time.monotonic() - started)
        except Exception as exc:
            self._error = f"{type(exc).__name__}: {exc}"
            logger.exception("Local LLM could not be loaded; Ava uses the rule-based engine.")
        finally:
            self._loading = False

    def is_ready(self) -> bool:
        return self._model is not None

    def status(self) -> dict:
        state = "ready" if self._model is not None else "loading" if self._loading else "error" if self._error else "idle"
        return {"provider": "local", "model": self.model_name, "device": self._device, "status": state,
                "error": self._error}

    # -- generation ------------------------------------------------------
    def complete(self, messages: list[dict], tools: list[dict]) -> LLMReply:
        if not self.is_ready():
            raise LLMUnavailable("Local LLM is not loaded yet")
        if not self._generate_lock.acquire(timeout=self.timeout):
            raise LLMUnavailable("Local LLM is busy")
        try:
            import torch

            inputs = self._tokenizer.apply_chat_template(
                messages, tools=tools or None, add_generation_prompt=True,
                return_tensors="pt", return_dict=True,
            ).to(self._device)
            prompt_length = inputs["input_ids"].shape[-1]
            sampling = {"do_sample": True, "temperature": self.temperature, "top_p": 0.9} \
                if self.temperature > 0 else {"do_sample": False}
            started = time.monotonic()
            with torch.inference_mode():
                output = self._model.generate(
                    **inputs,
                    max_new_tokens=self.max_new_tokens,
                    max_time=self.timeout,
                    pad_token_id=self._tokenizer.eos_token_id,
                    **sampling,
                )
            new_tokens = output[0][prompt_length:]
            elapsed = time.monotonic() - started
            text = self._tokenizer.decode(new_tokens, skip_special_tokens=True)
            logger.info("LLM generated %d tokens (prompt %d) in %.1fs", len(new_tokens), prompt_length, elapsed)
            if elapsed >= self.timeout and len(new_tokens) < self.max_new_tokens:
                raise LLMUnavailable("Local LLM timed out")
        except LLMUnavailable:
            raise
        except Exception as exc:
            logger.exception("Local LLM generation failed")
            raise LLMUnavailable(f"Generation failed: {type(exc).__name__}") from exc
        finally:
            self._generate_lock.release()
        return parse_model_output(text)


_client: LLMClient | None = None
_client_override: LLMClient | None = None
_client_lock = threading.Lock()


def set_llm_client(client: LLMClient | None) -> None:
    """Used by tests to inject a fake client."""
    global _client_override
    _client_override = client


def get_llm_client() -> LLMClient | None:
    global _client
    if _client_override is not None:
        return _client_override
    if not settings.llm_enabled:
        return None
    if settings.llm_provider != "local":
        logger.error("Unknown LLM_PROVIDER '%s'; the rule-based engine is used instead.", settings.llm_provider)
        return None
    with _client_lock:
        if _client is None:
            _client = LocalTransformersClient(
                model_name=settings.llm_model,
                device=settings.llm_device,
                max_new_tokens=settings.llm_max_new_tokens,
                timeout=settings.llm_timeout_seconds,
                temperature=settings.llm_temperature,
                threads=settings.llm_threads,
                cache_dir=settings.llm_cache_dir or None,
            )
    return _client


def start_llm() -> None:
    """Called on startup: begins loading the local model in the background."""
    client = get_llm_client()
    if isinstance(client, LocalTransformersClient):
        client.start_loading()


def llm_status() -> dict:
    client = get_llm_client()
    if client is None:
        return {"provider": "none", "status": "disabled"}
    if isinstance(client, LocalTransformersClient):
        return client.status()
    return {"provider": "custom", "status": "ready" if client.is_ready() else "loading"}
