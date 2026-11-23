# Skill 系统与演示页面设计

日期：2026-11-23
分支：feature/skill-system
状态：已与用户确认

## 1. 目标与范围

为 skill-find 实现一套 Skill 系统（发现、冲突裁决、注入、按需加载、热更新）与配套演示页面（skill 列表、对话窗口、评测结果表、调试面板）。

范围内：
- 后端 `app/services/skills/` 模块与相关 API
- LLM 封装扩展 tool calling（不改动现有 `chat()` 行为）
- 前端演示页面（左右双栏）
- 路由评测（按钮触发真实 LLM 评测，20 条）

范围外：
- 会话持久化（内存即可，重启清空）
- SSE 流式输出、文件 watcher
- skill 编辑/上传功能

已有素材（准备工作产物，直接使用）：
- `skills/`：6 个正常 skill，含 `templates/`、`scripts/` 附带文件
- `skills-extra/`：`broken-frontmatter-demo`（坏 frontmatter 样例）、`short-drama-script`（与主目录重名的冲突样例）
- `evals/routing-eval.jsonl`：20 条路由评测（normal 12 / boundary 1 / ambiguous 1 / no-skill 2 / hard-negative 4）

## 2. 已确认的关键决策

| 决策点 | 结论 |
|--------|------|
| agent 执行方式 | 真实 LLM tool-calling，后端跑 agent 循环 |
| 评测运行方式 | 页面按钮触发真实评测，单条单次 LLM 调用，结果缓存内存 |
| 冲突裁决 | 目录按配置顺序定优先级，先注册者胜；`skills/` > `skills-extra/`；落败方标记 overridden 并记录双方路径，不静默覆盖 |
| token 统计 | tiktoken（cl100k_base）估算，UI 标注为估算值 |
| 注入长度控制 | 预算默认 2000 token，超限三档降级：full → truncated（描述截断至 80 字）→ names_only |
| 模拟 200 skill | 内存合成 overlay，不落盘 |
| 热更新 | 每轮对话/每次列表请求前按 mtime 增量 refresh，无需重启 |
| 路径穿越防护 | 拒绝绝对路径；resolve 后强制校验位于该 skill 根目录内 |

## 3. 后端架构

### 3.1 模块划分（`backend/app/services/skills/`）

| 文件 | 职责 |
|------|------|
| `models.py` | Pydantic 模型：`SkillRecord`、`ScanIssue`、`InjectionResult`、`AgentEvent` 等 |
| `scanner.py` | 目录扫描与 frontmatter 解析、容错、冲突裁决 |
| `registry.py` | 扫描结果持有者；mtime 增量 refresh；200 合成 skill overlay；进程级单例 |
| `injector.py` | 注入文本拼接、tiktoken 计数、预算降级 |
| `files.py` | `read_skill_file` 安全读取 |
| `agent.py` | 单轮 agent 循环（tool-calling）、会话存储、事件记录 |
| `evals.py` | 路由评测执行与计分、结果内存缓存 |

### 3.2 scanner

- 输入：目录列表（配置顺序即优先级）。每个目录的一级子目录视为一个 skill 候选，读取其 `SKILL.md`。
- frontmatter 解析：文件必须以 `---` 行开头，找到闭合 `---` 行，中间块用 `yaml.safe_load` 解析为 dict；校验 `name`、`description` 均为非空字符串。
- 容错：任一候选解析失败（缺文件、无闭合分隔符、YAML 非法、字段缺失/类型错误）→ 记入 `ScanIssue(path, reason)`，跳过该 skill，不中断扫描，不影响服务启动。
- 冲突：`name` 已被先序目录注册 → 后来者生成 `SkillRecord(status="overridden", overridden_by=<胜者来源目录>)`，双方路径均记录；胜者保持 active。
- `SkillRecord` 字段：`name`、`description`、`source_dir`（相对仓库根，如 `skills`）、`skill_path`（SKILL.md 绝对路径）、`status`（active / overridden）、`mtime`。

### 3.3 registry

- `refresh()`：重新列目录，对比各 SKILL.md 的 mtime 与上次快照；仅对新增/修改/删除项重解析，重建冲突关系。目录不存在按空目录处理并记 issue。
- `force_rescan()`：全量重建（供「重新扫描」按钮）。
- `set_simulate(enabled)`：开启时叠加 200 个确定性合成 skill（`demo-skill-001` … `demo-skill-200`，描述约 40 字，正文为固定说明文本，可被 load_skill 加载）；关闭时移除。合成项 `source_dir="synthetic"`。
- 进程级单例，通过 FastAPI 依赖注入获取。

### 3.4 injector

- 注入格式：每个 active skill 一行 `- {name}: {description}`。
- 计数：tiktoken cl100k_base 对整段文本编码计数（估算值）。
- 降级：若 full 档超预算 → 每条描述截断至 `skill_desc_truncate_chars`（默认 80 字，尾部加 `…`）；仍超 → 仅 `- {name}` 列表。返回 `InjectionResult(text, tokens, strategy: full|truncated|names_only, budget, skill_count)`。
- 单 skill 的 `tokens` 字段 = 其 full 档单行的 token 数（用于列表展示）。

### 3.5 files（防路径穿越）

`read_skill_file(name, path)`：
1. name 必须是 registry 中 active skill，否则报错；
2. path 为绝对路径 → 拒绝；
3. `target = (skill_root / path).resolve()`，校验 `target.is_relative_to(skill_root.resolve())`，否则拒绝；
4. 文件不存在 / 非文件 / 超过 50KB → 报错；
5. 返回 UTF-8 文本内容。

所有错误以异常抛出，agent 循环将其转为 tool 错误结果返回给模型，不崩溃。

### 3.6 agent

- 会话：内存 dict `session_id -> list[ChatMessage]`（含 tool 消息）。
- 单轮流程：
  1. `registry.refresh()`（热更新：本轮即用新版本）；
  2. 构建 system prompt = 基础指令（说明可用工具、何时加载 skill）+ injector 注入文本；
  3. 调 `chat_with_tools`，工具为 `load_skill(name)`（返回去 frontmatter 的正文）与 `read_skill_file(name, path)`；
  4. 模型返回 tool_calls → 逐个执行、追加 tool 消息、记录 `AgentEvent`，继续循环；上限 `agent_max_tool_rounds`（默认 8），达到上限后强制不带 tools 收尾；
  5. 返回最终回复 + 事件流 + 本轮累计 usage（多次 LLM 调用求和，费用 6 位小数）+ 注入 token 数。
- `AgentEvent`：`type`（load_skill / read_skill_file）、`skill`、`path`（仅 read）、`ok`、`error`（失败原因）。
- 会话内已加载 skill 集合用于列表页 `loaded` 状态。

### 3.7 LLM 封装扩展

- `base.py` 新增：`ToolCall(id, name, arguments: str)`、`ToolChatResult(content: str | None, tool_calls: list[ToolCall], model, usage)`；`ChatMessage.role` 扩展 `tool`，新增可选 `tool_call_id`、`tool_calls` 字段；`LLMClient` Protocol 新增 `chat_with_tools(messages, tools)`。现有 `chat()` 不变。
- `openai_compatible.py` 实现：透传 tools 定义，解析响应 tool_calls；usage/费用复用现有逻辑（6 位小数）；错误映射沿用 `LLMNotConfiguredError`→503、`APIError`/解析异常→502。

### 3.8 evals

- 读取 `evals/routing-eval.jsonl`；逐条串行执行：system prompt 仅注入 name+description（模拟渐进加载第一层），要求模型只输出严格 JSON `{"action": "load"|"clarify"|"none", "skill": <name|null>}`。
- 计分：
  - normal / boundary：`action=load` 且 `skill == expected_skill` → pass；
  - ambiguous：`action=clarify` → pass；
  - no-skill / hard-negative：`action=none` → pass（其余 action 均判 fail）。
- 单条 LLM 失败或 JSON 解析失败 → 该行标 `error`，不中断整体。
- 结果缓存内存；重新扫描后缓存保留（页面提示可重跑）。

## 4. API 设计（均挂 `/api` 前缀，字段名英文）

| 方法/路径 | 请求 | 响应要点 |
|-----------|------|----------|
| `GET /api/skills?session_id=` | 可选 session_id | `skills[]`（name/description/source_dir/status/overridden_by/tokens/loaded）、`injection`（tokens/budget/strategy/skill_count）、`issues[]`（path/reason） |
| `POST /api/skills/rescan` | 无 | 强制全量重扫，返回同 GET 结构 |
| `POST /api/debug/simulate` | `{enabled: bool}` | 切换合成 overlay，返回同 GET 结构 |
| `POST /api/agent/chat` | `{session_id, message}` | `reply`、`events[]`、`usage`（input/output/total_tokens/cost）、`injection_tokens`、`tool_rounds` |
| `POST /api/evals/run` | 无 | `results[]`（id/query/category/expected_skill/actual/passed/error）、`summary`（total/passed/accuracy/by_category） |
| `GET /api/evals/results` | 无 | 上次评测缓存；无缓存返回 `results: []` |

错误：LLM 未配 key→503，上游失败→502，参数非法→422（沿用现有约定）。

## 5. 前端设计（Vue3 + TS，沿用 api/types/components 分层）

- `src/types/skill.ts`、`src/api/skills.ts`、`src/api/agent.ts`、`src/api/evals.ts`
- 组件：
  - `SkillList.vue`（左栏）：name、来源目录（skills→内置、skills-extra→团队共享、synthetic→模拟）、overridden 标记与胜者来源、单条 token、本会话 loaded 状态；issues 区块展示坏 skill 路径与原因；
  - `DebugPanel.vue`（左栏下方）：「重新扫描」按钮、「模拟 200 个 skill」开关、注入统计（token 数 / 预算 / 当前档位 full·truncated·names_only / skill 总数）；
  - `ChatPanel.vue`（右栏）：对话气泡；每轮 assistant 消息下方展示事件 chip（加载 skill ×N、读取文件 ×N，失败标红）与本轮 token/费用；session_id 前端生成（crypto.randomUUID）；
  - `EvalTable.vue`（右栏下方）：「运行评测」按钮（运行中禁用+进度提示）、结果表（id/query/category/expected/actual/passed）、按类别汇总正确率；页面加载时拉取缓存结果。
- `App.vue`：左右双栏布局，头部保留标题与 HealthStatus。
- 状态值英文：idle / loading / success / error。

## 6. 配置与依赖

`config.py` 新增（均可经 .env 覆盖）：
- `skill_dirs: list[str] = ["skills", "skills-extra"]`（相对仓库根解析，仓库根 = `Path(__file__).resolve().parents[3]`）
- `skill_injection_token_budget: int = 2000`
- `skill_desc_truncate_chars: int = 80`
- `agent_max_tool_rounds: int = 8`

依赖：`tiktoken`、`pyyaml`（若未在依赖中）；pyproject.toml 新增后必须在 backend 目录执行 `uv lock` 同步锁文件并 `uv lock --check` 验证。`.env.example` 同步新增配置模板。

## 7. 错误处理汇总

| 场景 | 行为 |
|------|------|
| frontmatter 损坏 | 跳过 + issues 记录原因，服务正常启动 |
| 重名冲突 | 先序目录胜，落败方 overridden 标记，不静默覆盖 |
| 路径穿越 / 绝对路径 / 越界 | tool 错误结果返回模型，不崩溃 |
| load 未知 skill | tool 错误结果 |
| LLM 未配 key / 上游失败 | 503 / 502 |
| 评测单条失败 | 该行 error，继续其余条目 |
| tool 循环达上限 | 强制不带 tools 收尾回答 |

## 8. 测试计划

pytest（backend 目录 `.venv\Scripts\python.exe -m pytest -q`）：
- scanner：6 正常 skill 解析、坏 frontmatter 跳过且 reason 明确、重名冲突裁决与 overridden 记录；
- injector：三档降级边界（构造恰好超预算的输入）、token 计数>0；
- files：`..` 穿越、绝对路径、不存在文件、超大文件均拒绝；合法附带文件可读；
- registry：修改 SKILL.md（mtime 变化）后 refresh 生效；新增/删除目录感知；simulate 开关叠加/移除 200 项；
- agent：FakeLLM 脚本化 tool_calls 验证循环、事件记录、轮次上限、错误转 tool 结果；
- evals：FakeLLM 验证各类别计分规则与单条失败不中断；
- API：httpx AsyncClient 集成测试覆盖各路由与错误码。

前端：`npm run build` 通过；`python dev.py` 启动后手工端到端验证（对话加载 skill、读附带文件、热更新、重新扫描、模拟 200、真实评测）。

## 9. 工程规则约束

- 代码、注释、标识符、API 字段、状态名、事件名一律英文；设计文档与 commit message 可中文。
- 费用保留 6 位小数；依赖变更同步 uv.lock。
- 新增文件需校验末尾换行符（字节级 0x0A）。
