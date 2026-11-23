# 大模型调用封装 + 单次 token/费用统计 设计文档

日期：2026-11-23
状态：已与用户确认

## 背景与目标

skill-find 后端已有 LLM 抽象雏形（`app/services/llm/` 下的 `LLMClient` Protocol 与
httpx 版 `OpenAICompatibleClient`），但只返回文本，无 token 统计与费用计算。

目标：

1. 基于官方 `openai` SDK（`AsyncOpenAI`）重写 OpenAI 兼容客户端封装。
2. 每次调用返回输入 token、输出 token、总 token 与费用（仅单次统计，不做累计/持久化）。
3. 全部配置放 `backend/.env`，改配置即可切换模型与单价，不改代码。
4. 新增 `POST /api/llm/chat` HTTP 接口，便于 curl/前端验证。

凭证来源：用户提供的阿里云百炼专属业务空间表格（apiKey + OpenAI 兼容地址）。
默认模型 `qwen-plus`，OpenAI 兼容 base_url 为
`https://llm-a0lz0dqy7z2w067m.cn-beijing.maas.aliyuncs.com/compatible-mode/v1`。

## 已确认的决策

| 决策点 | 结论 |
| --- | --- |
| 默认模型 | `qwen-plus`（.env 可改） |
| 费用计算 | .env 配置输入/输出单价（元/百万 token），费用 = token 数 × 单价 |
| 统计范围 | 仅单次调用统计，不累计、不持久化 |
| 暴露方式 | 服务层封装 + `POST /api/llm/chat` |
| 实现方案 | 方案 B：官方 openai SDK（AsyncOpenAI），替换现有 httpx 实现 |

## 配置层

`app/core/config.py` 的 `Settings` 保留现有字段，新增两项单价：

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `LLM_API_KEY` | `""` | 百炼 apiKey，真实值写入 backend/.env |
| `LLM_BASE_URL` | `https://api.openai.com/v1` | OpenAI 兼容地址 |
| `LLM_MODEL` | `gpt-4o-mini` | 模型名，.env 中设为 `qwen-plus` |
| `LLM_TIMEOUT_SECONDS` | `60.0` | 请求超时 |
| `LLM_INPUT_PRICE_PER_MILLION` | `0.8` | 输入单价，元/百万 token |
| `LLM_OUTPUT_PRICE_PER_MILLION` | `2.0` | 输出单价，元/百万 token |

`backend/.env`（gitignore 已覆盖，不提交）写入真实 key、百炼兼容地址、
`qwen-plus` 与上述单价；`backend/.env.example` 同步更新为占位模板。
切换模型 = 修改 `LLM_MODEL` 与两个单价。

## 服务层

依赖：`backend/pyproject.toml` 新增 `openai`。

### 契约（app/services/llm/base.py）

- `ChatMessage`：保持不变（role: system/user/assistant，content: str）。
- 新增 `LLMUsage`（Pydantic）：`input_tokens: int`、`output_tokens: int`、
  `total_tokens: int`、`cost: float`（单位元，保留 6 位小数）。
- 新增 `ChatResult`（Pydantic）：`content: str`、`model: str`、`usage: LLMUsage`。
- `LLMClient` Protocol：`async def chat(messages: list[ChatMessage]) -> ChatResult`。
- 异常保持不变：`LLMError`、`LLMNotConfiguredError`。

### 实现（app/services/llm/openai_compatible.py）

- 改用 `AsyncOpenAI(api_key=..., base_url=..., timeout=...)`。
- `chat()` 调 `client.chat.completions.create(model=..., messages=...)`（非流式）。
- 从响应 `usage.prompt_tokens / completion_tokens / total_tokens` 取 token 数；
  `total_tokens` 缺失时用 input + output 兜底。
- 费用 = `input_tokens / 1e6 × 输入单价 + output_tokens / 1e6 × 输出单价`，
  `round(..., 6)`。
- 单价由构造函数注入（来自 Settings），客户端本身不读环境变量。

### 工厂（app/services/llm/__init__.py，沿用现有位置）

扩展现有 `get_llm_client() -> LLMClient`：从 `get_settings()` 读配置构建
`OpenAICompatibleClient`（含单价注入）。业务代码只依赖工厂与 Protocol。

## HTTP 接口

`POST /api/llm/chat`（挂现有 `/api` 路由前缀）。

请求体：

```json
{"messages": [{"role": "user", "content": "你好"}]}
```

响应 200：

```json
{
  "reply": "你好！……",
  "model": "qwen-plus",
  "usage": {
    "input_tokens": 12,
    "output_tokens": 34,
    "total_tokens": 46,
    "cost": 0.000078
  }
}
```

schema 放 `app/schemas/llm.py`，路由放 `app/api/routes/llm.py`，
复用现有 router 注册方式。

## 错误处理

| 场景 | 服务层异常 | HTTP 状态码 |
| --- | --- | --- |
| 未配置 API key | `LLMNotConfiguredError` | 503 |
| 网络/HTTP 失败（openai.APIError 等） | `LLMError` | 502 |
| 响应缺 `usage` 或 `choices` 为空 | `LLMError` | 502 |
| 请求体校验失败 | — | 422（FastAPI 默认） |

错误响应体沿用 FastAPI `{"detail": "..."}` 格式。

## 测试

pytest 单元测试（不发起真实付费调用）：

- mock SDK 客户端：usage 解析正确、费用计算正确（含 6 位小数舍入）。
- 响应缺 usage / choices 为空 → `LLMError`。
- 未配 key → `LLMNotConfiguredError`。
- SDK 抛 API 错误 → 映射为 `LLMError`。
- API 层用假客户端覆盖依赖：200 / 503 / 502 三条路径。

真实 key 的端到端 curl 验证由用户在验收时自行决定执行。

## 语言规则

代码、注释、标识符、API 路径与字段一律英文；本文档与 commit message 用中文。

## 范围外（YAGNI）

- 流式输出、重试、并发限流。
- 累计统计、持久化、费用看板。
- 内置模型价格表、多模型路由。
- 前端页面改动。