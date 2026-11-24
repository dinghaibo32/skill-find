# 会话记录摘要：Skill 样例与路由评测集

- 日期：2026-11-23 ~ 2026-11-24
- 分支：feature/llm-usage-cost（产物现已随 main 分支可见）
- 产物：`skills/`（6 个正常 skill）、`skills-extra/`（2 个异常样例）、`evals/routing-eval.jsonl`（20 条路由评测）

## 一、任务目标

1. 按 `skills/<name>/SKILL.md` 格式编写至少 6 个 skill 样例：
   - frontmatter 仅含 `name` 与 `description`，正文写具体步骤；
   - 至少 2 个 skill 带附带文件（模板/脚本），按需读取、按需运行；
   - 其中 2 个 skill 描述相近、容易混淆；
2. 在第二个目录准备 1 个 frontmatter 格式错误的 skill 和 1 个与已有 skill 同名的 skill；
3. 编写 15-20 条用户请求的路由评测集，每条标注应使用的 skill，包含不需要任何 skill 的情况。

## 二、最终目录结构

```
skills/                                  # 主目录：6 个正常 skill
├── short-drama-script/                  # 易混淆对 ①：从零写短剧剧本
│   ├── SKILL.md
│   ├── templates/script-template.md     # 附带模板，逐集写作阶段才读取
│   └── scripts/check.py                 # 附带脚本，自检阶段才运行
├── short-drama-dialogue-polish/         # 易混淆对 ②：只改写已有剧本台词
│   └── SKILL.md
├── python-env-doctor/                   # Python 环境故障诊断
│   ├── SKILL.md
│   └── scripts/diagnose.py              # 只读环境快照，诊断开始时运行一次
├── csv-data-cleaning/SKILL.md           # CSV 数据清洗
├── api-smoke-test/                      # API 冒烟测试
│   ├── SKILL.md
│   └── templates/request-template.json  # 构造写接口请求时才读取
└── chinese-commit-message/SKILL.md      # 中文提交信息规范

skills-extra/                            # 第二目录：2 个异常样例
├── broken-frontmatter-demo/SKILL.md     # frontmatter 缺少闭合 ---，故意写坏
└── short-drama-script/SKILL.md          # 与主目录同名，故意重名冲突

evals/
└── routing-eval.jsonl                   # 20 条路由评测用例
```

## 三、关键设计决策

### 渐进加载（三层）

1. 平时 agent 只看到每个 skill 的 `name` + 一句话 `description`；
2. 判断需要某 skill 时才加载 SKILL.md 正文；
3. 正文提到附带文件时，才按需读取模板 / 运行脚本（正文中明确标注"仅在 X 阶段才读取/运行"）。

### 易混淆对

- `short-drama-script`（写短剧剧本）与 `short-drama-dialogue-polish`（改写短剧台词）描述高度相近；
- 双方在 description 与正文中写明互斥边界："从无到有（含新增场景/剧情）" vs "只改台词表达、剧情信息量不变"；
- polish 正文明确：用户要新增场景或改剧情走向时转用 script。

### 异常样例的期望行为

- 坏 frontmatter 样例：加载器应报解析错误并跳过，而非崩溃或把正文当描述；
- 重名样例：加载器应报冲突并列出两个来源路径，按优先级保留一个，不得静默覆盖；其正文步骤与主版本刻意不同，便于识别实际加载了哪个。

### 语言规则

遵循项目规范：脚本代码、注释、docstring 用英文；SKILL.md 文档正文与评测用例用中文。

## 四、路由评测集（evals/routing-eval.jsonl）

每行一个 JSON 对象：`id / query / expected_skill / category / reason`，`expected_skill` 为 `null` 表示不需要任何 skill。

| 类别 | 条数 | 说明 |
|------|------|------|
| normal | 12 | 6 个 skill 各 2 条明确命中 |
| boundary | 1 | #5 有旧剧本但要加场景改剧情 → short-drama-script |
| ambiguous | 1 | #6 "剧本整体改一改" → 期望先澄清而非盲目加载 |
| no-skill | 2 | #15 代码阅读问答、#20 新功能设计 |
| hard-negative | 4 | 含 skill 关键词但不应触发 |

hard-negative 设计意图（测误触发）：

- #16 git rebase/merge 知识问答 → 不应触发 chinese-commit-message；
- #17 短剧行业咨询 → 不应触发两个短剧 skill；
- #18 pytest 断言失败查代码逻辑 → 不应触发 python-env-doctor（非环境故障）；
- #19 写脚本把 CSV 转 JSON → 不应触发 csv-data-cleaning（格式转换非清洗）。

使用建议：评测时只注入各 skill 的 name + description（模拟渐进加载第一层），比对 agent 选择与 expected_skill；ambiguous 条目单独按"是否发起澄清"计分。

## 五、验证结果（实际执行）

1. frontmatter 校验：6 个主 skill 均含 name/description 且解析通过；坏样例被正确识别为无法闭合；重名样例被检出双来源；
2. `diagnose.py` 运行 exit=0（只读快照）；
3. `check.py` 对合法剧本样例 exit=0、非法样例 exit=1；期间修复一个真实 bug：钩子行 `**【本集结尾钩子】**：` 的 Markdown 加粗符号导致正则漏匹配（HOOK_RE 增加 `\*{0,2}`，台词计数排除钩子行）；
4. 评测集 20 行 JSON 全部合法，skill 标注与 `skills/` 实际 name 一致；
5. 全部新建文件通过末尾换行字节级校验（Write 工具多次丢失末尾换行，均已批量补齐）。

## 六、遗留事项

- 无未完成的代码改动；临时校验脚本已清理；
- 评测集尚未接入自动化评测 runner（当前为数据文件，供后续 skill-find 路由功能消费）。
