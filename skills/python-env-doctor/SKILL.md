---
name: python-env-doctor
description: 当 Python 项目出现环境类故障（ModuleNotFoundError、pip/uv 安装失败、虚拟环境激活异常、Python 版本不匹配、依赖锁文件冲突）需要诊断时使用。典型说法："跑不起来，缺包"、"venv 好像坏了"、"uv sync 报错"。
---

# Python 环境诊断

## 概述

按固定顺序采集证据、定位环境故障根因，再给出最小修复方案。核心原则：先诊断后动手，禁止一上来就重装环境或删锁文件。

## 使用步骤

1. **采集现场**：运行附带诊断脚本，一次性收集环境快照（仅在诊断开始时运行一次）：

   ```bash
   python scripts/diagnose.py
   ```

   输出：Python 解释器路径与版本、是否在 venv 内、pip/uv 可用性、关键包版本、`pyproject.toml` 与锁文件是否存在。
2. **复现错误**：让用户提供完整报错栈，或亲自运行触发命令复现。只依据真实报错定位，不猜测。
3. **按表定位**：

   | 症状 | 优先怀疑 | 验证方式 |
   |------|---------|---------|
   | ModuleNotFoundError | 解释器与安装环境不一致 | 对比 `sys.executable` 与包安装位置 |
   | 安装解析失败 | 版本约束冲突 / 源不可达 | 读报错中的 conflict 段 |
   | venv 激活无效 | PATH 顺序 / 激活脚本未执行 | `where python`（Windows）或 `which python` |
   | 锁文件冲突 | 依赖变更后未重新锁定 | 对比 pyproject 与 lock 的修改时间 |
4. **最小修复**：只修根因对应的一项（如用对解释器重装单个包、重新 `uv lock`）。每步修复后重跑触发命令验证。
5. **禁止项**：未经用户确认不得删除 `.venv`、`uv.lock`、全局 site-packages 内容；不得建议"全部重装"作为第一方案。

## 常见错误

- 看到缺包就 `pip install`，结果装进了系统 Python 而非项目 venv。
- 只看报错最后一行，忽略上方的依赖解析冲突详情。
