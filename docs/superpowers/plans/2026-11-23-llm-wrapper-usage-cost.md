# 大模型调用封装 + 单次 token/费用统计 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 基于官方 openai SDK 封装 LLM 调用，每次返回输入/输出 token 与费用，配置全部走 backend/.env，并提供 POST /api/llm/chat 验证接口。

**Architecture:** 服务层 `OpenAICompatibleClient` 用 `AsyncOpenAI` 调 OpenAI 兼容接口，从响应 usage 计算 token 与费用（单价由 Settings 注入）；`get_llm_client()` 工厂读配置构建客户端；FastAPI 路由通过 `Depends(get_llm_client)` 注入，异常映射为 503/502。

**Tech Stack:** Python 3.13（backend/.venv）、FastAPI、pydantic-settings、openai SDK、pytest。

**设计文档:** `docs/superpowers/specs/2026-11-23-llm-wrapper-usage-cost-design.md`

**约定:**
- 所有 pytest 命令在 `D:\dhb\code\bishi\skill-find\backend` 目录下执行，解释器用 `.venv\Scripts\python.exe`。
- 代码、注释、标识符一律英文；commit message 用中文。
- 真实 API key 只写入 `backend/.env`（已 gitignore），严禁出现在任何被提交的文件中。
- 异步服务层测试用 `asyncio.run(...)` 包在同步测试函数里，不引入 pytest-asyncio。

---

### Task 1: 依赖与配置（单价字段）

**Files:**
- Modify: `backend/pyproject.toml`（dependencies 段）
- Modify: `backend/app/core/config.py`（Settings 类 LLM 段末尾）
- Test: `backend/tests/test_config.py`（新建）

- [ ] **Step 1: 写失败测试**

新建 `backend/tests/test_config.py`：

```python
"""Tests for LLM-related settings."""

from app.core.config import Settings


def test_llm_price_defaults() -> None:
    settings = Settings(_env_file=None)
    assert settings.llm_input_price_per_million == 0.8
    assert settings.llm_output_price_per_million == 2.0


def test_llm_prices_overridable() -> None:
    settings = Settings(
        _env_file=None,
        llm_input_price_per_million=1.5,
        llm_output_price_per_million=6.0,
    )
    assert settings.llm_input_price_per_million == 1.5
    assert settings.llm_output_price_per_million == 6.0
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/test_config.py -v`
Expected: FAIL（pydantic 忽略未知字段，默认值断言不成立 / 字段不存在）

- [ ] **Step 3: 最小实现**

`backend/pyproject.toml` 的 `dependencies` 列表追加一行：

```toml
    "openai>=1.40",
```

`backend/app/core/config.py` 在 `llm_timeout_seconds: float = 60.0` 之后追加：

```python
    # Pricing in CNY per 1M tokens; adjust together with llm_model.
    llm_input_price_per_million: float = 0.8
    llm_output_price_per_million: float = 2.0
```

- [ ] **Step 4: 安装依赖**

Run（任意目录）: `D:\dhb\code\bishi\skill-find\backend\.venv\Scripts\python.exe -m pip install -e "D:\dhb\code\bishi\skill-find\backend[dev]"`
Expected: 成功安装 openai 及其依赖

- [ ] **Step 5: 运行确认通过**

Run: `.venv\Scripts\python.exe -m pytest tests/test_config.py -v`
Expected: 2 passed

- [ ] **Step 6: Commit**

```bash
git add backend/pyproject.toml backend/uv.lock backend/app/core/config.py backend/tests/test_config.py
git commit -m "feat: 配置新增 LLM 输入/输出单价字段并引入 openai SDK 依赖"
```

注：若 pip 安装未更新 `backend/uv.lock`，则只 add 实际变更的文件（用 `git status` 确认）。

---

### Task 2: 服务层契约（LLMUsage / ChatResult / Protocol）

**Files:**
- Modify: `backend/app/services/llm/base.py`
- Test: `backend/tests/test_llm_base.py`（新建）

- [ ] **Step 1: 写失败测试**

新建 `backend/tests/test_llm_base.py`：

```python
"""Tests for LLM contract models."""

from app.services.llm.base import ChatResult, LLMUsage


def test_llm_usage_fields() -> None:
    usage = LLMUsage(input_tokens=12, output_tokens=34, total_tokens=46, cost=0.000078)
    assert usage.total_tokens == 46
    assert usage.cost == 0.000078


def test_chat_result_fields() -> None:
    result = ChatResult(
        content="hello",
        model="qwen-plus",
        usage=LLMUsage(input_tokens=1, output_tokens=2, total_tokens=3, cost=0.0),
    )
    assert result.content == "hello"
    assert result.model == "qwen-plus"
    assert result.usage.output_tokens == 2
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/test_llm_base.py -v`
Expected: FAIL（ImportError: cannot import name 'ChatResult'）

- [ ] **Step 3: 最小实现**

`backend/app/services/llm/base.py`：在 `ChatMessage` 类之后新增两个模型，并把 Protocol 的返回类型改为 `ChatResult`。改后文件完整内容：

```python
"""Vendor-agnostic LLM contracts.

Define the message shape and the client protocol here; concrete
implementations (OpenAI-compatible, local models, mocks) live alongside.
"""

from typing import Literal, Protocol

from pydantic import BaseModel


class ChatMessage(BaseModel):
    """A single chat turn sent to the model."""

    role: Literal["system", "user", "assistant"]
    content: str


class LLMUsage(BaseModel):
    """Token counts and cost for a single LLM call. Cost is in CNY."""

    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost: float


class ChatResult(BaseModel):
    """Assistant reply plus per-call usage statistics."""

    content: str
    model: str
    usage: LLMUsage


class LLMError(Exception):
    """Base error for LLM call failures."""


class LLMNotConfiguredError(LLMError):
    """Raised when an LLM call is attempted without an API key configured."""


class LLMClient(Protocol):
    """Minimal contract every LLM implementation must satisfy."""

    async def chat(self, messages: list[ChatMessage]) -> ChatResult:
        """Send chat messages and return the reply with usage statistics."""
        ...
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv\Scripts\python.exe -m pytest tests/test_llm_base.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/llm/base.py backend/tests/test_llm_base.py
git commit -m "feat: LLM 契约新增 LLMUsage/ChatResult，chat 返回回复与用量"
```

---

### Task 3: 用 openai SDK 重写客户端（usage 解析 + 费用计算）

**Files:**
- Modify: `backend/app/services/llm/openai_compatible.py`（整文件重写）
- Test: `backend/tests/test_llm_client.py`（新建）

- [ ] **Step 1: 写失败测试**

新建 `backend/tests/test_llm_client.py`：

```python
"""Tests for the openai-SDK based LLM client (no real network calls)."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from openai import APIConnectionError

from app.services.llm import openai_compatible
from app.services.llm.base import ChatMessage, LLMError, LLMNotConfiguredError
from app.services.llm.openai_compatible import OpenAICompatibleClient


def _response(content="hi", prompt_tokens=1000, completion_tokens=500, total_tokens=1500):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        ),
    )


def _patch_sdk(monkeypatch, response=None, error=None):
    fake = MagicMock()
    if error is not None:
        fake.chat.completions.create = AsyncMock(side_effect=error)
    else:
        fake.chat.completions.create = AsyncMock(return_value=response)
    fake.close = AsyncMock()
    monkeypatch.setattr(openai_compatible, "AsyncOpenAI", lambda **kwargs: fake)
    return fake


def _client(api_key="sk-test"):
    return OpenAICompatibleClient(
        api_key=api_key,
        base_url="https://example.com/v1",
        model="qwen-plus",
        input_price_per_million=0.8,
        output_price_per_million=2.0,
    )


def _chat(client):
    return asyncio.run(client.chat([ChatMessage(role="user", content="hello")]))


def test_chat_returns_content_and_usage(monkeypatch):
    _patch_sdk(monkeypatch, response=_response())
    result = _chat(_client())
    assert result.content == "hi"
    assert result.model == "qwen-plus"
    assert result.usage.input_tokens == 1000
    assert result.usage.output_tokens == 500
    assert result.usage.total_tokens == 1500
    assert result.usage.cost == 0.0018


def test_cost_rounded_to_six_decimals(monkeypatch):
    _patch_sdk(
        monkeypatch,
        response=_response(prompt_tokens=12, completion_tokens=34, total_tokens=46),
    )
    result = _chat(_client())
    assert result.usage.cost == 0.000078


def test_total_tokens_fallback(monkeypatch):
    _patch_sdk(monkeypatch, response=_response(total_tokens=None))
    result = _chat(_client())
    assert result.usage.total_tokens == 1500


def test_missing_usage_raises(monkeypatch):
    response = _response()
    response.usage = None
    _patch_sdk(monkeypatch, response=response)
    with pytest.raises(LLMError):
        _chat(_client())


def test_empty_choices_raises(monkeypatch):
    response = _response()
    response.choices = []
    _patch_sdk(monkeypatch, response=response)
    with pytest.raises(LLMError):
        _chat(_client())


def test_none_content_raises(monkeypatch):
    _patch_sdk(monkeypatch, response=_response(content=None))
    with pytest.raises(LLMError):
        _chat(_client())


def test_sdk_error_mapped_to_llm_error(monkeypatch):
    error = APIConnectionError(
        request=httpx.Request("POST", "https://example.com/v1/chat/completions")
    )
    _patch_sdk(monkeypatch, error=error)
    with pytest.raises(LLMError):
        _chat(_client())


def test_missing_api_key_raises():
    with pytest.raises(LLMNotConfiguredError):
        _chat(_client(api_key=""))
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/test_llm_client.py -v`
Expected: FAIL（TypeError: 构造函数不接受 input_price_per_million）

- [ ] **Step 3: 最小实现**

`backend/app/services/llm/openai_compatible.py` 整文件替换为：

```python
"""LLM client for any OpenAI-compatible endpoint, built on the openai SDK.

Works with OpenAI, DeepSeek, Qwen (DashScope compatible mode), Ollama,
vLLM, etc. Only `base_url`, `api_key`, `model` and prices differ per vendor.
"""

from openai import APIError, AsyncOpenAI

from app.services.llm.base import (
    ChatMessage,
    ChatResult,
    LLMError,
    LLMNotConfiguredError,
    LLMUsage,
)


class OpenAICompatibleClient:
    """Async client speaking the OpenAI chat completions protocol."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: float = 60.0,
        input_price_per_million: float = 0.0,
        output_price_per_million: float = 0.0,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._input_price = input_price_per_million
        self._output_price = output_price_per_million

    async def chat(self, messages: list[ChatMessage]) -> ChatResult:
        """Call chat completions and return the reply with usage statistics."""
        if not self._api_key:
            raise LLMNotConfiguredError(
                "LLM API key is not configured. Set LLM_API_KEY in backend/.env."
            )

        client = AsyncOpenAI(
            api_key=self._api_key,
            base_url=self._base_url,
            timeout=self._timeout_seconds,
        )
        try:
            response = await client.chat.completions.create(
                model=self._model,
                messages=[message.model_dump() for message in messages],
            )
        except APIError as exc:
            raise LLMError(f"LLM request failed: {exc}") from exc
        finally:
            await client.close()

        try:
            content = response.choices[0].message.content
        except (AttributeError, IndexError, TypeError) as exc:
            raise LLMError(f"Unexpected LLM response shape: {response}") from exc
        if content is None:
            raise LLMError("LLM response has empty content")

        usage = response.usage
        if usage is None:
            raise LLMError("LLM response is missing usage statistics")
        input_tokens = usage.prompt_tokens
        output_tokens = usage.completion_tokens
        total_tokens = usage.total_tokens or input_tokens + output_tokens
        cost = round(
            input_tokens / 1_000_000 * self._input_price
            + output_tokens / 1_000_000 * self._output_price,
            6,
        )
        return ChatResult(
            content=content,
            model=self._model,
            usage=LLMUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                cost=cost,
            ),
        )
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv\Scripts\python.exe -m pytest tests/test_llm_client.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/llm/openai_compatible.py backend/tests/test_llm_client.py
git commit -m "feat: 用 openai SDK 重写 LLM 客户端，返回单次 token 与费用"
```

---

### Task 4: 工厂注入单价 + 导出新契约

**Files:**
- Modify: `backend/app/services/llm/__init__.py`（整文件重写）
- Test: `backend/tests/test_llm_factory.py`（新建）

- [ ] **Step 1: 写失败测试**

新建 `backend/tests/test_llm_factory.py`：

```python
"""Tests for the settings-driven LLM client factory."""

from app.core.config import Settings
from app.services import llm
from app.services.llm.openai_compatible import OpenAICompatibleClient


def test_factory_uses_settings(monkeypatch):
    settings = Settings(
        _env_file=None,
        llm_api_key="sk-test",
        llm_base_url="https://example.com/v1",
        llm_model="qwen-max",
        llm_input_price_per_million=2.4,
        llm_output_price_per_million=9.6,
    )
    monkeypatch.setattr(llm, "get_settings", lambda: settings)
    client = llm.get_llm_client()
    assert isinstance(client, OpenAICompatibleClient)
    assert client._model == "qwen-max"
    assert client._input_price == 2.4
    assert client._output_price == 9.6
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/test_llm_factory.py -v`
Expected: FAIL（`_input_price` 为默认 0.0，断言 2.4 不成立）

- [ ] **Step 3: 最小实现**

`backend/app/services/llm/__init__.py` 整文件替换为：

```python
"""LLM integration layer.

Model calls go through the `LLMClient` protocol so routes and services
never depend on a concrete vendor SDK.
"""

from app.core.config import get_settings
from app.services.llm.base import (
    ChatMessage,
    ChatResult,
    LLMClient,
    LLMError,
    LLMNotConfiguredError,
    LLMUsage,
)
from app.services.llm.openai_compatible import OpenAICompatibleClient

__all__ = [
    "ChatMessage",
    "ChatResult",
    "LLMClient",
    "LLMError",
    "LLMNotConfiguredError",
    "LLMUsage",
    "OpenAICompatibleClient",
    "get_llm_client",
]


def get_llm_client() -> LLMClient:
    """Factory for the default LLM client, driven by settings."""
    settings = get_settings()
    return OpenAICompatibleClient(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        timeout_seconds=settings.llm_timeout_seconds,
        input_price_per_million=settings.llm_input_price_per_million,
        output_price_per_million=settings.llm_output_price_per_million,
    )
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv\Scripts\python.exe -m pytest tests/test_llm_factory.py -v`
Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/llm/__init__.py backend/tests/test_llm_factory.py
git commit -m "feat: LLM 工厂注入单价配置并导出用量契约"
```

---

### Task 5: HTTP 接口 POST /api/llm/chat

**Files:**
- Create: `backend/app/schemas/llm.py`
- Create: `backend/app/api/routes/llm.py`
- Modify: `backend/app/api/router.py`
- Test: `backend/tests/test_llm_api.py`（新建）

- [ ] **Step 1: 写失败测试**

新建 `backend/tests/test_llm_api.py`：

```python
"""Tests for POST /api/llm/chat using a fake LLM client."""

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.llm import get_llm_client
from app.services.llm.base import ChatResult, LLMError, LLMNotConfiguredError, LLMUsage


class _FakeClient:
    def __init__(self, result=None, error=None):
        self._result = result
        self._error = error

    async def chat(self, messages):
        if self._error is not None:
            raise self._error
        return self._result


def _client_with(fake):
    app = create_app()
    app.dependency_overrides[get_llm_client] = lambda: fake
    return TestClient(app)


def _result():
    return ChatResult(
        content="hello there",
        model="qwen-plus",
        usage=LLMUsage(input_tokens=12, output_tokens=34, total_tokens=46, cost=0.000078),
    )


def _payload():
    return {"messages": [{"role": "user", "content": "hi"}]}


def test_chat_returns_reply_and_usage():
    client = _client_with(_FakeClient(result=_result()))
    response = client.post("/api/llm/chat", json=_payload())
    assert response.status_code == 200
    body = response.json()
    assert body["reply"] == "hello there"
    assert body["model"] == "qwen-plus"
    assert body["usage"] == {
        "input_tokens": 12,
        "output_tokens": 34,
        "total_tokens": 46,
        "cost": 0.000078,
    }


def test_chat_not_configured_returns_503():
    client = _client_with(_FakeClient(error=LLMNotConfiguredError("no key")))
    response = client.post("/api/llm/chat", json=_payload())
    assert response.status_code == 503


def test_chat_upstream_failure_returns_502():
    client = _client_with(_FakeClient(error=LLMError("boom")))
    response = client.post("/api/llm/chat", json=_payload())
    assert response.status_code == 502


def test_chat_empty_messages_returns_422():
    client = _client_with(_FakeClient(result=_result()))
    response = client.post("/api/llm/chat", json={"messages": []})
    assert response.status_code == 422
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/test_llm_api.py -v`
Expected: FAIL（404，路由不存在）

- [ ] **Step 3: 最小实现**

新建 `backend/app/schemas/llm.py`：

```python
"""Schemas for the LLM chat endpoint."""

from pydantic import BaseModel, Field

from app.services.llm.base import ChatMessage, LLMUsage


class ChatRequest(BaseModel):
    """Payload for POST /api/llm/chat."""

    messages: list[ChatMessage] = Field(min_length=1)


class ChatResponse(BaseModel):
    """Reply text plus per-call token and cost statistics."""

    reply: str
    model: str
    usage: LLMUsage
```

新建 `backend/app/api/routes/llm.py`：

```python
"""LLM chat endpoint exposing the service-layer client."""

from fastapi import APIRouter, Depends, HTTPException

from app.schemas.llm import ChatRequest, ChatResponse
from app.services.llm import get_llm_client
from app.services.llm.base import LLMClient, LLMError, LLMNotConfiguredError

router = APIRouter(tags=["llm"])


@router.post("/llm/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    client: LLMClient = Depends(get_llm_client),
) -> ChatResponse:
    """Send messages to the configured model and return reply with usage."""
    try:
        result = await client.chat(request.messages)
    except LLMNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ChatResponse(reply=result.content, model=result.model, usage=result.usage)
```

`backend/app/api/router.py` 整文件替换为：

```python
"""Router aggregation.

- root_router: public endpoints mounted at "/" (e.g. /health).
- api_router: business endpoints mounted under "/api".
"""

from fastapi import APIRouter

from app.api.routes import health, llm

root_router = APIRouter()
root_router.include_router(health.router)

api_router = APIRouter(prefix="/api")
api_router.include_router(llm.router)
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv\Scripts\python.exe -m pytest tests/test_llm_api.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/llm.py backend/app/api/routes/llm.py backend/app/api/router.py backend/tests/test_llm_api.py
git commit -m "feat: 新增 POST /api/llm/chat 接口返回回复与单次用量"
```

---

### Task 6: .env 配置落地 + 全量回归 + 可选真实冒烟

**Files:**
- Modify: `backend/.env.example`
- Create: `backend/.env`（不提交，含真实 key）

- [ ] **Step 1: 更新 .env.example**

`backend/.env.example` 整文件替换为：

```dotenv
# Copy to backend/.env and fill in real values. Never commit .env.

# --- LLM settings (any OpenAI-compatible provider) ---
LLM_API_KEY=
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
LLM_TIMEOUT_SECONDS=60

# Pricing in CNY per 1M tokens (defaults match qwen-plus).
LLM_INPUT_PRICE_PER_MILLION=0.8
LLM_OUTPUT_PRICE_PER_MILLION=2.0
```

- [ ] **Step 2: 从用户表格生成 backend/.env（key 不落聊天/不提交）**

新建临时脚本 `backend/tmp_write_env.py`（执行后删除）：

```python
"""One-off helper: write backend/.env from the Bailian apiKey xlsx."""
import xml.etree.ElementTree as ET
import zipfile

XLSX = r"C:\Users\hypo\Desktop\默认业务空间-apiKey-7786983 (1).xlsx"
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

with zipfile.ZipFile(XLSX) as z:
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        root = ET.fromstring(z.read("xl/sharedStrings.xml"))
        shared = [
            "".join(t.text or "" for t in si.iter(NS + "t"))
            for si in root.findall(NS + "si")
        ]
    root = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
    values = {}
    for c in root.iter(NS + "c"):
        v = c.find(NS + "v")
        text = v.text if v is not None else ""
        if c.get("t") == "s" and text:
            text = shared[int(text)]
        values[c.get("r")] = text

env = (
    f"LLM_API_KEY={values['B2']}\n"
    f"LLM_BASE_URL={values['B4']}\n"
    "LLM_MODEL=qwen-plus\n"
    "LLM_TIMEOUT_SECONDS=60\n"
    "LLM_INPUT_PRICE_PER_MILLION=0.8\n"
    "LLM_OUTPUT_PRICE_PER_MILLION=2.0\n"
)
with open(r"D:\dhb\code\bishi\skill-find\backend\.env", "w", encoding="utf-8") as f:
    f.write(env)
print("backend/.env written (key not printed)")
```

Run: `.venv\Scripts\python.exe tmp_write_env.py`
Expected: 输出 `backend/.env written (key not printed)`
然后删除 `backend/tmp_write_env.py`。

- [ ] **Step 3: 确认 .env 被 git 忽略**

Run: `git -C D:\dhb\code\bishi\skill-find check-ignore backend/.env`
Expected: 输出 `backend/.env`（若未被忽略，先把它加入 .gitignore 再继续）

- [ ] **Step 4: 全量回归**

Run: `.venv\Scripts\python.exe -m pytest -v`
Expected: 全部 passed（health 2 + config 2 + base 2 + client 8 + factory 1 + api 4 = 19）

- [ ] **Step 5: Commit**

```bash
git add backend/.env.example
git commit -m "chore: .env.example 补充 LLM 单价配置模板"
```

- [ ] **Step 6: 可选真实冒烟（会产生少量费用，先征得用户同意）**

启动后端（后台）: `.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000`
Run: `curl -s -X POST http://127.0.0.1:8000/api/llm/chat -H "Content-Type: application/json" -d "{\"messages\":[{\"role\":\"user\",\"content\":\"用一句话介绍你自己\"}]}"`
Expected: 200，JSON 含 `reply`、`model=qwen-plus`、`usage`（token 数为正、cost > 0）。
验证后停止后端进程。若用户不同意真实调用，跳过本步。

---

## 自审记录

- 规格覆盖：配置层→Task 1/6；契约→Task 2；SDK 实现与费用→Task 3；工厂→Task 4；HTTP 接口与错误映射→Task 5；.env/.env.example/测试→Task 1-6。无遗漏。
- 无占位符；所有代码步骤含完整代码。
- 类型一致性：`LLMUsage/ChatResult` 字段、`input_price_per_million/output_price_per_million` 参数名、`_input_price/_output_price` 属性名在 Task 3/4/5 间一致；费用示例 0.000078 与设计文档一致。