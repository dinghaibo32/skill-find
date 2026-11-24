# 会话工作总结：大模型调用封装 + 单次 token/费用统计

日期：2026-11-24
分支：`feature/llm-usage-cost`（14 个提交，按用户选择保留未合并）
相关文档：
- 设计文档：`docs/superpowers/specs/2026-11-23-llm-wrapper-usage-cost-design.md`
- 实施计划：`docs/superpowers/plans/2026-11-23-llm-wrapper-usage-cost.md`

## 一、需求

1. 添加大模型调用封装，统计每次调用的输入 token、输出 token、费用。
2. 配置全部放 `backend/.env`。
3. 凭证来自阿里云百炼专属业务空间表格（apiKey + OpenAI 兼容地址），要求改配置即可切换模型。

## 二、已确认的关键决策

| 决策点 | 结论 |
| --- | --- |
| 默认模型 | `qwen-plus`（.env 可改） |
| 费用计算 | .env 配置输入/输出单价（元/百万 token），费用 = token 数 × 单价，保留 6 位小数 |
| 统计范围 | 仅单次调用统计，不累计、不持久化 |
| 暴露方式 | 服务层封装 + `POST /api/llm/chat` HTTP 接口 |
| 实现方案 | 官方 openai SDK（AsyncOpenAI），替换原 httpx 实现（用户选定方案 B） |
| 工作方式 | 新建特性分支开发（非 worktree、非直接 main） |
| 执行方式 | 子代理驱动开发：每任务实现 + 规格审查 + 质量审查双重门禁 |

## 三、交付内容

| 层 | 文件 | 说明 |
| --- | --- | --- |
| 配置 | `backend/app/core/config.py` | 新增 `llm_input_price_per_million=0.8`、`llm_output_price_per_million=2.0` |
| 契约 | `backend/app/services/llm/base.py` | `LLMUsage`（input/output/total_tokens + cost，CNY）、`ChatResult`（content/model/usage），Protocol 返回 `ChatResult` |
| 实现 | `backend/app/services/llm/openai_compatible.py` | `AsyncOpenAI` 调 chat completions；费用计算；缺 usage/空 choices/空内容/畸形 usage 均映射 `LLMError`；`finally` 关闭客户端 |
| 工厂 | `backend/app/services/llm/__init__.py` | `get_llm_client()` 注入全部配置含单价，re-export 新契约 |
| Schema | `backend/app/schemas/llm.py` | `ChatRequest`（messages 非空）、`ChatResponse`（reply/model/usage） |
| 路由 | `backend/app/api/routes/llm.py` + `router.py` | `POST /api/llm/chat`，`Depends(get_llm_client)` 注入 |
| 依赖 | `backend/pyproject.toml` + `uv.lock` | `openai>=1.40`（实际锁定 3.57.0），锁文件已同步 |
| 配置落地 | `backend/.env`（未提交）+ `.env.example` | 真实 key + 百炼兼容地址 + qwen-plus + 单价 |
| 测试 | `backend/tests/test_config.py` 等 5 个文件 | 共 22 个用例 |

### 错误处理语义

| 场景 | 服务层异常 | HTTP |
| --- | --- | --- |
| 未配置 API key | `LLMNotConfiguredError` | 503 |
| 网络/HTTP 失败、畸形响应 | `LLMError` | 502 |
| 请求体校验失败（空 messages、非法 role） | — | 422 |

## 四、切换模型方式（只改 .env，不动代码）

```dotenv
LLM_MODEL=qwen-max                # 换模型名
LLM_INPUT_PRICE_PER_MILLION=2.4   # 换对应输入单价
LLM_OUTPUT_PRICE_PER_MILLION=9.6  # 换对应输出单价
```

## 五、执行过程

6 个任务均按 TDD（红→绿→提交）执行，每任务经过规格符合性审查 + 代码质量审查，审查发现的问题全部修复并复审：

1. **Task 1** 依赖与配置：修复 uv.lock 失同步（`uv lock`）、补末尾换行。
2. **Task 2** 服务层契约：一次通过（换行问题随 Task 3 修复）。
3. **Task 3** SDK 客户端：补 close/SDK 构造参数/create 入参断言；`total_tokens` 回退改显式 None 判断；修复测试数据使其具备变异区分性（经变异验证）。
4. **Task 4** 工厂接线：补 timeout 透传断言。
5. **Task 5** HTTP 接口：补消息透传断言与非法 role 422 用例。
6. **Task 6** .env 落地：多消息保序断言、单价模板换模型提示。

最终整体审查后收尾修复：usage token 字段为 None 时统一映射 `LLMError`（避免 500）、更新过时配置注释。

### 提交清单（main..feature/llm-usage-cost）

```
bc0706f fix: usage 字段异常统一映射 LLMError，更新配置注释
cdab103 test: 多消息透传断言；docs: 单价模板补充换模型提示
93ad57a chore: .env.example 补充 LLM 单价配置模板
22e1145 test: 补充消息透传断言与非法 role 校验用例
a1882c3 feat: 新增 POST /api/llm/chat 接口返回回复与单次用量
703ea00 test: 工厂测试补充 timeout 透传断言
99989bb feat: LLM 工厂注入单价配置并导出用量契约
9b64b2a test: 增强 total_tokens 回退用例的回归区分性
2079abb test: 补充 SDK 参数与资源释放断言，显式处理 total_tokens 回退
3b4d496 feat: 用 openai SDK 重写 LLM 客户端，返回单次 token 与费用
7b712bb style: 补齐 LLM 契约与测试文件末尾换行符
7ceb73a feat: LLM 契约新增 LLMUsage/ChatResult，chat 返回回复与用量
5a69862 chore: 同步 uv.lock 补充 openai 依赖并补齐测试文件末尾换行
6314553 feat: 配置新增 LLM 输入/输出单价字段并引入 openai SDK 依赖
```

## 六、验证结果

- **单元测试**：`backend` 目录 `.venv\Scripts\python.exe -m pytest -q` → **22 passed**（health 2 + config 2 + base 2 + client 10 + factory 1 + api 5）。
- **锁文件**：`uv lock --check` 通过，openai 锁定 3.57.0 与 venv 一致。
- **安全**：`backend/.env` 被 gitignore 且全历史从未提交；用真实 key 字面值扫描全部提交，0 泄露。
- **真实冒烟**（用户授权执行）：`POST /api/llm/chat` 调百炼 qwen-plus 成功——

```json
{
  "reply": "我是通义千问（Qwen）……",
  "model": "qwen-plus",
  "usage": {"input_tokens": 12, "output_tokens": 61, "total_tokens": 73, "cost": 0.000132}
}
```

费用核算验证：12×0.8/1e6 + 61×2.0/1e6 = 0.0001316 → round 6 位 = 0.000132 ✓

## 七、遗留事项与后续建议

1. **分支未合并**：`feature/llm-usage-cost` 保留现状，用户自行决定合并时机。
2. **公网部署前**：`/api/llm/chat` 需加鉴权/限流（当前无鉴权即可触发付费调用）；502 detail 透传上游错误原文，公网化时建议收敛为通用文案 + 日志。
3. **messages 无长度上限**：对外暴露前建议加 `Field(max_length=...)` 护栏控制单请求费用。
4. **可选增强**（均超出本次范围）：流式输出、重试、累计统计/持久化、504 超时细分。

## 八、过程经验

- Write 工具可能丢失文件末尾换行，写入后需字节级校验（已多次复现并修复）。
- PowerShell 下 curl 发 JSON 用 `-d @文件` 避免引号转义失败。
- 后端新增依赖必须同步 `uv lock`，否则 `uv sync --locked` 会失败。
- 回归测试数据要具备变异区分性（如 total_tokens=0 用例需让 input/output 非零才能捕获 `or` 回退缺陷）。