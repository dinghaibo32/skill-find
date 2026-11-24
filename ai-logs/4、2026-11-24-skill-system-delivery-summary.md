# Skill 系统交付总结

> 日期：2026-11-24 · 分支：`feature/skill-system`（已合并，最终成果在 `main`，HEAD `470822c`，已推送 origin）
> 执行方式：brainstorming → 设计规格 → writing-plans → 子代理驱动开发（每任务实现 + 规格审查 + 质量审查双关卡）→ 全量验证 → 合并收尾

---

## 1. 需求与验收基准

### Skill 系统（后端）

| 能力 | 要求 |
|---|---|
| 发现 | 扫描多个目录（内置/团队共享）解析 SKILL.md frontmatter；格式错误跳过并报告原因，一个坏 skill 不能让整个系统启动不了 |
| 冲突 | 两个目录同名 skill 的裁决规则自定 |
| 注入 | 所有 skill 名字+描述拼入 system prompt 并统计 token；说明 skill 很多（如 200 个）时如何控制长度 |
| 加载 | `load_skill(name)` 工具返回正文；`read_skill_file(name, path)` 读取附带文件，防止路径穿越 |
| 热更新 | skill 文件修改后下一轮对话即生效，无需重启 |

### 演示页面（前端）

- 左栏：skill 列表（来源目录、是否被覆盖、token 占用、加载状态）
- 右栏：对话窗口，每轮显示加载了哪些 skill、读取了哪些附带文件
- 评测结果表格
- 调试面板：重新扫描按钮 + 模拟 200 个 skill 开关

素材使用准备工作中备好的 `skills/`（6 个正常 skill）、`skills-extra/`（坏 frontmatter + 重名冲突样例）、`evals/routing-eval.jsonl`（20 条评测）。

## 2. 设计决策（用户已确认）

| 决策点 | 结论 |
|---|---|
| Agent 执行方式 | 真实 LLM tool-calling（后端 agent 循环，产生真实 API 费用） |
| 评测运行方式 | 页面按钮触发真实评测（20 条串行单次调用，结果缓存内存） |
| 总体方案 | 方案 A：后端分层模块 + 每轮 mtime 增量重扫 |
| 冲突优先级 | `skills/` > `skills-extra/`（先注册者胜，落败方标 `overridden` 并记录 `overridden_by`） |
| token 估算 | tiktoken `cl100k_base`（qwen 实际分词略有差异，UI 标注估算） |
| 注入预算 | 2000 token 三档降级：full → truncated（描述截 80 字加 …）→ names_only（兜底可能仍超预算，契约已声明） |
| 模拟 200 | 内存合成 overlay（demo-skill-001..200），不落盘，走完整注入管线真实触发降级 |
| 路径穿越防护 | 拒绝绝对路径 → `(root/path).resolve()` → `is_relative_to(root)` 双重校验 |

产物：

- 设计规格：`docs/superpowers/specs/2026-11-23-skill-system-design.md`（提交 `e75d6ce`）
- 实施计划：`docs/superpowers/plans/2026-11-23-skill-system.md`（提交 `31fa638`，13 个 TDD 任务，含完整测试与实现代码）

## 3. 架构与模块

```
backend/app/
├── core/config.py              # skill_dirs / 预算 / 截断字数 / 轮次上限 / get_repo_root
├── services/skills/
│   ├── models.py               # SkillRecord / ScanIssue / ScanResult / InjectionResult / AgentEvent
│   ├── scanner.py              # frontmatter 解析（顶格 --- 判定）+ 目录扫描容错 + 冲突裁决
│   ├── injector.py             # count_tokens / skill_line / build_injection 三档降级
│   ├── files.py                # read_skill_file 安全读取（穿越/50KB/编码容错）
│   ├── registry.py             # mtime 快照热更新 + force_rescan + 200 合成开关 + 单例
│   ├── agent.py                # AgentService：会话历史/tool 循环/事件/usage 累计/轮次上限
│   └── evals.py                # EvalService：分类计分/单条容错/raw_decode 解析/缓存
├── services/llm/base.py        # ToolCall / ToolChatResult / ChatMessage 扩展（tool role）
├── services/llm/openai_compatible.py  # chat_with_tools（payload 形状零回归）
├── schemas/skills.py           # API DTO（SkillInfo/InjectionInfo/AgentChatResponse 等）
├── schemas/llm.py              # PublicChatMessage 隔离 tool role（422 校验不回归）
└── api/routes/                 # skills.py / agent.py / evals.py（错误码 503/502/422）

frontend/src/
├── types/skill.ts              # 与后端 schema 逐字段镜像
├── api/                        # http.ts（统一错误 detail 提取）+ skills/agent/evals 封装
├── components/                 # SkillList / DebugPanel / ChatPanel / EvalTable
└── App.vue                     # 双栏布局 360px+1fr，sessionId=crypto.randomUUID()
```

API 一览：`GET /api/skills?session_id=`、`POST /api/skills/rescan`、`POST /api/debug/simulate`、`POST /api/agent/chat`、`POST /api/evals/run`、`GET /api/evals/results`。

## 4. 13 任务执行与审查记录

每任务流程：实现者（TDD：RED→GREEN→提交）→ 规格合规审查 → 代码质量审查 → 发现问题派修复 → 复审。测试数全程递增、零回归。

| # | 任务 | 实现提交 | 修复/补强提交 | 测试数 | 审查发现与修复要点 |
|---|---|---|---|---|---|
| 1 | 依赖、配置与样例素材 | `416199b` | `091d9d0` | 24 | 素材既有缺陷：check.py 把出场行误计台词、diagnose.py 空输出 IndexError |
| 2 | Skill 模型与扫描器 | `9416661` | `39058cc` | 36 | 块标量内缩进 `---` 误判为结束符（改顶格 rstrip 判定）；stat/iterdir 移入 try 容错 |
| 3 | 注入器（tiktoken+三档降级） | `8a4a02e` | `4878e2a` | 42 | approve；补兜底档契约 docstring 与等值边界测试 |
| 4 | 安全文件读取 | `703e38c` | `0fe83a4` | 50 | UnicodeDecodeError 泄漏契约（GBK 文件）→ 统一映射 SkillFileError；补恰好 50KB 边界 |
| 5 | 注册表（热更新+模拟200） | `4f1b888` | `4de9ca1` | 58 | 快照阶段 OSError 缺口（每轮必经路径）；force_rescan 先快照后扫描时序；补"无变化不重扫"性能契约测试。计划 fixture 缺陷（mkdir 重复）裁定接受 |
| 6 | LLM tool-calling 扩展 | `7ce2877` | `ac98f3c` | 66 | PublicChatMessage 隔离 + payload 只输出非空字段，两处既有测试零回归；补组合响应测试与 fake 存根 |
| 7 | Agent 循环服务 | `0f34ebf` | `1562912` | 74 | 计划代码缺陷：收尾路径漏 append 最终 assistant 消息（跨轮历史丢失）；FakeLLM 快照存引用改浅拷贝；load_skill 漏接 UnicodeDecodeError；loaded_skills 返回内部 set 改拷贝 |
| 8 | 路由评测服务 | `0913339` | `986254e` `fc855a8` | 84 | 提示词 JSON 示例花括号转义丢失（规格审查字节级比对发现）；非字符串 action 抛 TypeError 逃逸容错（set→元组）；raw_decode 提取首个 JSON；坏行报错补文件行号 |
| 9 | API 路由层 | `344add1` | `fc7f4af` | 92 | 计划 fixture 缺陷：dependency_overrides 每请求新建实例丢跨请求状态（改共享实例，裁定接受）；补 rescan 强断言、502 路径测试、端点 docstring |
| 10 | 前端类型与 API 层 | `505c7f4` | `ab10593` | 92 | 统一 getJson/postJson 错误 detail 提取；422 数组 detail 改 JSON.stringify（原 String() 显示 [object Object]） |
| 11 | SkillList + DebugPanel | `653163e` | `9f9dd13` | 92 | 受控 checkbox 请求失败后视觉错位（onToggle 立即回写 prop 值）；同目录同名 skill 组合 key 冲突（掺 index）；计划文本同步修订 |
| 12 | ChatPanel + EvalTable + 布局 | `c043c80` | `e51b5f9` | 92 | 预授权修复 handler 缺 catch；#app max-width 720px 锁死双栏（改 1200px）；暗色模式气泡浅底文字不可读（固定深色） |
| 13 | 全量验证与收尾 | `54ff056` | — | 92 | 端到端验收 12/12 PASS（见下节）；README 追加演示说明 |

整体最终审查（`e75d6ce^..54ff056` 全量 28 提交）结论 **Ready to merge**，遗留 2 Minor + 1 加固项随后修复并复审 approve：

- `f0270d3`：扫描器两处 `is_dir()` 纳入 OSError 守护（PermissionError 不再中断扫描）；read_skill_file 分支兜底 ValueError（Py3.12 NUL 路径防御）
- `470822c`：SkillsResponse 增加 `simulating` 字段，前端开关状态以服务端为准（修复页面刷新后开关脱同步）

最终测试数：**95 passed**。

## 5. 验证结果

### 自动化验证

| 项 | 结果 |
|---|---|
| 后端全量测试 | 95 passed, 0 failed（scanner 14 / evals 10 / files 8 / registry 8 / agent 9 / api 8 / llm_tools 7 / injector 6 / llm_api 5 / config 4 + 既有） |
| 依赖锁文件 | `uv lock --check` 通过（43 packages） |
| 前端构建 | `vue-tsc --noEmit && vite build` 通过，无类型错误 |
| 既有契约回归 | `/api/llm/chat` 角色校验 422、payload 形状断言、`/health` 全部零回归 |

### 真实 LLM 端到端验收（API 级，12/12 PASS）

| 项 | 实测结果 |
|---|---|
| 发现/冲突/容错 | 6 active + skills-extra 重名标「被覆盖 ← skills」+ broken-frontmatter-demo issue（missing closing '---'）；注入 full / 701 tok / 预算 2000 |
| 真实对话+按需加载 | 「写一个 8 集的逆袭短剧剧本…」→ load_skill ok=true，tool_rounds=1，3336 tok，费用 ¥0.004076，单轮 27.3s；随后列表 loaded=true |
| 路径穿越防护 | 诱导读 `../../backend/.env` → 事件 ok=false，error="path escapes the skill directory"，无内容泄漏，服务不崩溃 |
| 热更新 | 修改 csv-data-cleaning 描述 → 不重启即生效 → 字节级恢复原文 → rescan 还原 |
| 重新扫描 | 200，列表完整 |
| 模拟 200 | ON → 206 条（6 真实 active + 200 合成）/ names_only / 1437 tok ≤ 2000；OFF → full / 701 tok |
| 真实评测 | 20 行，**accuracy 0.95（19/20）**：normal 12/12、hard-negative 4/4、no-skill 2/2、boundary 1/1、ambiguous 0/1（id=6 模糊指令模型判定偏差，非代码缺陷）；缓存逐字段一致 |
| 错误码 | 空 message → 422（string_too_short） |

验证局限：无浏览器环境，UI 渲染由 vue-tsc + 构建 + 逐组件审查覆盖；真实模型输出非确定性，重跑结果可能不同。

## 6. 合并收尾

- `feature/skill-system` → `feature/llm-usage-cost`：fast-forward（`bc0706f..470822c`），60 文件，+6628/−49
- 合并后复验：95 passed / uv lock --check / 前端构建 全部通过
- 功能分支已删除；成果现已在 `main` 并推送 `origin/main`（HEAD `470822c`）
- 测试临时文件已清理，工作区干净

## 7. 已知权衡与残留事项（演示定位，审查裁定可接受）

| 项 | 说明 |
|---|---|
| 会话内存无界 / 单例无锁 | 演示项目定位，非生产系统 |
| refresh 竞态 | turn-complete 与手动操作并发 last-write-wins，下次操作自愈 |
| mtime 粒度 | 同 tick 连续修改 refresh 可能漏检，「重新扫描」按钮兜底 |
| ChatPanel 不自动滚动 | 长对话需手动滚动 |
| crypto.randomUUID | 需安全上下文（localhost 满足；局域网裸 HTTP 访问会白屏） |
| tiktoken 首次联网 | cl100k_base 编码文件首次使用需下载，离线环境首请求会失败 |
| 模拟开关开启时评测 | 以 206 条 names_only 目录参评，accuracy 解读需注意 |
| evals 路由守护性死分支 | 服务层已行级容错，外层 503/502 仅防御未来扩展（注释已说明） |

## 8. 工程实践沉淀

- **TDD 全程**：每任务先 RED 后 GREEN，修复项均要求变异/反事实证明回归断言捕获力
- **双审查关卡**：规格审查（逐字比对、不信报告独立验证）+ 质量审查（实证探针），13 任务共发现并修复 20+ 处问题，其中 4 处为计划自身缺陷（实现者最小修复 + 审查裁定 + 计划同步修订）
- **兼容性隔离**：公开 schema 与内部协议分层（PublicChatMessage），扩展 tool calling 零回归
- **语言规则**：代码/注释/标识符/API 字段英文，commit message 与 UI 文案中文
- **依赖纪律**：依赖变更同步 `uv lock`，收尾 `uv lock --check`
- **文件末尾换行**：Write 工具可能丢末尾换行，所有新文件提交前字节级校验末字节 0x0A

## 9. 启动与演示

```bash
python dev.py        # 后端 8000 + 前端 5173
# 打开 http://localhost:5173
```

演示动线：左栏看列表与冲突标记 → 对话触发 load_skill/read_skill_file chip → 改 SKILL.md 验证热更新 → 开「模拟 200」看 names_only 降级 → 「运行评测」看 20 条真实路由结果。
