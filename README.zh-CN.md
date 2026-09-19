# CONTINUUM · 续境

**工具可以换，上下文不必重来。**

面向人和 Coding Agent 的本地对话历史底座。[English](README.md)

目标很简单：连接获准读取的本机 AI 工具记录，让人通过 GUI 搜索阅读，
让 Agent 通过 MCP 查询其他工具的历史。保留原文出处，不改写各家的原生会话库。

## 当前状态

**这是可运行的开源开发地基，不是已经适配三家的完整产品。**

已实现：规范化快照 v1、SQLite 原子导入、全文/短中文检索、来源引用、版本绑定分页、
CLI、4 个只读 MCP 工具、失败回滚测试、真实 stdio 协议测试、构建与 CI、
Cursor IDE `state.vscdb` 只读导入经 CLI/stdio/隔离 wheel（合成夹具；未做真实宿主验收）、
以 CLI JSON 为底座的 GUI 会话和 Vite 壳（pytest；未做浏览器端到端）。

未实现：Claude Code / Codex 读取器、Cursor JSONL 与自动发现、实时更新、浏览器端到端 GUI、
桌面安装包（无 `.app` / `.exe`）、PyPI 上的 `continuum-history`、细粒度客户端权限、
附件读取、跨 Agent 执行。

仓库只有人工编写的合成示例，没有私人对话、旧归档、本机配置或凭据。
之前的个人 Cursor 原型没有直接打包进来。

## 跑起来

先安装 [uv](https://docs.astral.sh/uv/getting-started/installation/)，需要 Python 3.12+。
**没有** PyPI 包，**没有** 桌面安装包。不要 `pip install continuum`（那是别人的
PyTorch 持续学习库）。GitHub prerelease 有 wheel：

```sh
uv pip install \
  https://github.com/bosprimigenious/continuum/releases/download/v0.1.0a1/continuum_history-0.1.0a1-py3-none-any.whl
continuum --help
```

从源码：

```sh
git clone https://github.com/bosprimigenious/continuum.git
cd continuum
uv sync --locked
uv run continuum --db .continuum/demo.sqlite3 import examples/synthetic.snapshot.json
uv run continuum --db .continuum/demo.sqlite3 search "数据库锁"
uv run continuum --db .continuum/demo.sqlite3 sources
uv run continuum --db .continuum/demo.sqlite3 list
```

复制搜索返回的 `session_id` 或列表中的 `id`，运行：

```sh
uv run continuum --db .continuum/demo.sqlite3 read SESSION_ID --limit 2
```

返回的 `next_cursor` 可通过 `--cursor` 继续读取；`null` 表示结束。
重复导入相同快照得到 `changed: false`，原文件不变。

默认 `import` 仍只接受 Continuum 快照 v1。显式指定适配器后可导入一份自选的
Cursor `state.vscdb`（需要 `--source-id`，不会扫描家目录）。读取时复制主库和
WAL/SHM 再只读打开，不写源文件。结构损坏的采集会 `incomplete_source`，不覆盖已有索引，
也不会为失败导入新建空 `--db`。真实 Cursor 库不要提交进仓库；JSONL / 工作区库不在
这一适配器范围内。

相同 `source_id` 的新导入会原子替换该来源的派生索引，不是历史版本并集；
新快照缺少的旧事件会从索引移除。请保留源文件，不把索引当备份。

## MCP

```sh
uv run continuum --db .continuum/demo.sqlite3 serve
```

提供 `history_sources`、`history_list`、`history_search`、`history_read`。
客户端配置示例见 [英文 README](README.md#connect-an-mcp-client)。
已经测试 SDK 客户端与真实 stdio 子进程的完整往返；还没有验收三家真实宿主。

连接客户端意味着允许它读取**整个指定索引**。项目筛选不是权限隔离；
不同信任范围请使用不同索引。通过 MCP 交给 Agent 的片段可能进入其模型服务，
不能把“本地索引”理解成“后续绝不出网”。

## 技术路线

- 当前：Python 3.12+、uv、Pydantic v2、SQLite/FTS5、官方 MCP SDK v2。
- 质量：pytest、Ruff、mypy、锁定依赖、GitHub Actions。
- GUI：React / TypeScript / Vite，经 `continuum` CLI JSON 访问索引；桌面壳仍是 Tauri 2，未开工。
- 架构：模块化单体，一个核心、多种入口；不引入云账号、向量数据库或执行调度服务。

在仓库 `gui/` 目录 `npm install && npm run dev`。这不是桌面安装包，也不在 foundation gate 里跑。

## 开发与完成标准

```sh
uv sync --locked
uv run python scripts/check.py
```

统一门禁检查格式、lint、严格类型、测试与覆盖率、基础发布隐私规则、构建和隔离安装。
它可能下载构建依赖，不会读取本机原生对话。CI 覆盖 Linux / macOS / Windows，
通过仅代表当前地基，不代表真实 Cursor 宿主、桌面包或 PyPI 已上架。
PyPI 的预定路径是 GitHub OIDC Trusted Publishing（`publish.yml`），在
pypi.org 登记 pending publisher 之前保持未发布。

下一步限定为一个可安装、可追溯、能读到末尾的 Cursor 只读适配器，
再扩其他来源与 GUI。不因为发现竞品而重新扩大或推倒整个范围。

[架构与取舍](docs/architecture.md) · [开发手册](docs/development.md) ·
[贡献规范](CONTRIBUTING.md) · [隐私与安全](SECURITY.md)

MIT 开源。索引明文保存，不承诺自动完整脱敏或安全擦除。独立项目，与各厂商无隶属关系。
