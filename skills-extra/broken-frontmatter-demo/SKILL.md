---
name: broken-frontmatter-demo
description: 这是一个故意写坏 frontmatter 的样例：缺少结束的 --- 分隔符，YAML 块无法闭合。加载器应报错或跳过本 skill。

# 错误 Frontmatter 样例

## 说明

本文件是**故意的坏样例**，用于测试 skill 加载器的容错：

1. frontmatter 只有开头的 `---`，没有闭合的 `---`；
2. 解析器会把正文也当成 YAML，导致解析失败或字段污染；
3. 期望行为：加载器报 frontmatter 解析错误，跳过本 skill，而不是崩溃或把正文当描述。

## 正文步骤（若被错误加载才会看到）

1. 这一步不应该被执行。
2. 如果你的 agent 读到了这里，说明 frontmatter 校验缺失。
