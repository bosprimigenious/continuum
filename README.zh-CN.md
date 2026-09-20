<div align="center">

<img src="gui/src-tauri/icons/icon.png" width="96" height="96" alt="Continuum">

# Continuum · 续境

**工具可以换，上下文不必重来。**

给人和 Coding Agent 用的本地对话历史。
你指定文件，它建成索引；CLI、MCP、GUI 查的是同一份库。
不改写各家原生会话数据库。

[![CI](https://github.com/bosprimigenious/continuum/actions/workflows/ci.yml/badge.svg)](https://github.com/bosprimigenious/continuum/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/bosprimigenious/continuum?include_prereleases)](https://github.com/bosprimigenious/continuum/releases)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![pre-alpha](https://img.shields.io/badge/status-pre--alpha-orange)

[English](README.md) · [架构](docs/architecture.md) · [发布](docs/publishing.md) · [贡献](CONTRIBUTING.md) · [安全](SECURITY.md) · [Release](https://github.com/bosprimigenious/continuum/releases)

</div>

---

Continuum 是一个**本机**索引：你选出已经在磁盘上的对话，导入派生 SQLite，然后搜索、读完、通过 MCP 交给另一个 Agent。

它**不会**扫描家目录，**不会**对 Cursor / Claude Code / Codex 的库做写入，也**没有**把对话传到 Continuum 自己的服务器。当前是 pre-alpha：Cursor 路径有合成夹具和门禁，真实宿主未验收；PyPI 尚未上架。

## 目录

- [先跑起来](#先跑起来)
- [安装](#安装)
- [CLI](#cli)
- [MCP](#mcp)
- [GUI](#gui)
- [已实现 / 未实现](#已实现--未实现)
- [怎么拼起来的](#怎么拼起来的)
- [参与开发](#参与开发)
- [隐私](#隐私)
- [常见问题](#常见问题)
- [许可](#许可)

## 先跑起来

需要 [uv](https://docs.astral.sh/uv/getting-started/installation/) 和 Python 3.12+。

```sh
git clone https://github.com/bosprimigenious/continuum.git
cd continuum
uv sync --locked

uv run continuum --db .continuum/demo.sqlite3 import examples/synthetic.snapshot.json
uv run continuum --db .continuum/demo.sqlite3 search "数据库锁"
```

应命中一条预览里带 `SQLite 数据库锁` 的结果。复制 `session_id`：

```sh
uv run continuum --db .continuum/demo.sqlite3 read SESSION_ID --limit 2
```

跟着 `next_cursor` 走到 `null`。再导入同一文件会得到 `"changed": false`，示例文件不会被改。

仓库里只有手写合成 JSON，没有私人对话。

## 安装

**不要 `pip install continuum`。** 那个名字是别人的 PyTorch 持续学习库。

| 渠道 | 状态 |
| --- | --- |
| GitHub prerelease wheel `v0.1.0a1` | 有 |
| PyPI 项目名 `continuum-history` | **未发布。** OIDC 422 `invalid-publisher`：pypi.org 上还没有 pending publisher。维护者步骤见 [publishing.md](docs/publishing.md) |
| 已签名桌面安装包 | 未发布 |
| Windows `.exe` | CI 打出未签名 NSIS（`Continuum_0.1.0-alpha.1_x64-setup.exe`）。启动/查询未在 Windows 上跑过 |

从 GitHub Release 装：

```sh
uv pip install \
  https://github.com/bosprimigenious/continuum/releases/download/v0.1.0a1/continuum_history-0.1.0a1-py3-none-any.whl
continuum --help
```

从源码请用上一节的 `uv run continuum …`。命令行入口是 `continuum`；将来上 PyPI 的发行名是 `continuum-history`。

## CLI

索引路径用 `--db` 或环境变量 `CONTINUUM_DB`。不扫家目录，也不猜厂商库位置。

```sh
uv run continuum --db .continuum/demo.sqlite3 import examples/synthetic.snapshot.json

export CONTINUUM_DB=.continuum/demo.sqlite3
uv run continuum search "数据库锁"
uv run continuum "数据库锁"
uv run continuum --format text search "数据库锁"
uv run continuum read SESSION_ID --limit 2
```

`--format auto`（默认）：管道里是 JSON（给 GUI/MCP/脚本），终端里是可读文本。
`--format json` 永远 JSON。这不是 Grok/Codex 那种 agent REPL，只查你已经导入的索引。

搜索是字面 Unicode（含短中文）。命中给 240 字 **preview**；全文只在 `read`。
按来源 / 项目过滤是精确匹配，不是权限。

### Cursor `state.vscdb`

只覆盖一种观察到的 IDE 形态，不是 Cursor 的全部存储。文件路径由你提供，Continuum 不会去找。
真实 Cursor 安装 **未验收**。

```sh
uv run continuum --db .continuum/demo.sqlite3 import \
  --adapter cursor-state-vscdb --source-id cursor-demo PATH/TO/state.vscdb
```

`--source-id` 必填。读取时复制主库和 WAL/SHM，再 `mode=ro` 打开副本。
阻塞失败（`incomplete_source`）不会覆盖已有索引，也不会为失败导入新建空 `--db`。

不要把真实 Cursor 库提交进 git。agent-transcripts JSONL、工作区 sidebar DB 不是这个适配器。
重复使用同一个 `source_id` 会**整份替换**该来源的派生快照，不是历史并集。源文件请自己留着，索引可以扔掉重导。

## MCP

同一份索引，四只读工具。导入只走 CLI。

```sh
uv run continuum --db .continuum/demo.sqlite3 serve
```

```json
{
  "mcpServers": {
    "continuum": {
      "command": "uv",
      "args": [
        "run", "--locked", "--directory", "/absolute/path/to/continuum",
        "continuum", "--db", "/absolute/path/to/continuum/.continuum/demo.sqlite3", "serve"
      ]
    }
  }
}
```

两个路径都换成你机器上的绝对路径。各宿主的配置文件位置不一样。

| 工具 | 作用 |
| --- | --- |
| `history_sources` | 已导入来源、条数、摘要、时间 |
| `history_list` | 列会话，可按来源 / 项目过滤 |
| `history_search` | 字面子串搜索 |
| `history_read` | 全文、分页、`source_ref` |

没有 import 工具，不接受文件系统路径，不能删源，也不能「让另一个 Agent 去执行」。
对 Python SDK 的 stdio 往返测过；Cursor / Claude Code / Codex **宿主**没测过。

**连上客户端 = 它可以读完这个索引。** 项目过滤不是 ACL。不同信任范围用不同 `--db`。
Agent 读到的正文仍可能被宿主发到模型服务。Continuum 自己没有上传通道。

本机 Coding Agent 用中枢 skill `continuum-history`（`~/shared-ai-skills/continuum-history/`，软链到 Grok / Claude / Codex / Cursor 的 `skills/`）。按那份 `SKILL.md` 走 CLI 或已连接的 MCP，不要另写扫家目录的脚本。合成自检：

```sh
bash ~/shared-ai-skills/continuum-history/scripts/continuum_skill_check.sh
```

## GUI

界面只调 CLI 的 JSON，自己不解析厂商文件、不直接打开 SQLite。
桌面壳是四屏工作台（会话列表、阅读、覆盖、设置），不是编辑器，也不是第二套 agent。

**Vite 开发壳**（要 checkout，不是安装包）：

```sh
cd gui
npm install
npm run dev
```

**桌面**还是实验性质。本仓库可以打一份**未签名**的 macOS `.app`（PyInstaller 把 `continuum` CLI 冻成 sidecar）。
没有公证、不进 git、也不是干净机器安装包。Windows NSIS 由 GitHub `windows-latest` 打出，本机 macOS 不能启动该 `.exe`。

```sh
uv run --with pyinstaller python scripts/build_sidecar.py
uv run python scripts/smoke_sidecar.py
cd gui && npm ci && npx tauri build
```

需要 Rust（`rustup`）和 Node。产物在 `gui/src-tauri/target/release/bundle/`（已 gitignore）。

## 已实现 / 未实现

pre-alpha。地基门禁绿只说明 **这份 checkout** 能过，不说明产品做完。

| 仓库里有的 | 还没有 |
| --- | --- |
| 快照 v1 导入、字面搜索、分页、出处 | Claude Code / Codex 适配器 |
| Cursor `state.vscdb` / `cursorDiskKV`（合成夹具） | 真实 Cursor 宿主、JSONL、sidebar DB |
| CLI + 四只读 MCP，共用一个核心 | 自动发现、后台增量刷新 |
| GUI 走 CLI JSON；Vite；本机未签名 macOS `.app`；CI 有 Windows NSIS 工件 | 浏览器 e2e、已签名安装包、Windows 启动/查询验收 |
| GitHub `v0.1.0a1` wheel；Linux / macOS / Windows CI | PyPI `continuum-history` |
| 回滚、Unicode、WAL 边车、stdio 测试 | 语义搜索、附件全文、云同步 |

原生适配器在记下「具名 Cursor × OS × MCP 宿主」组合之前报 **NOT READY**。
GUI 在真实浏览器或桌面点选路径走通之前报 **NOT READY**。

## 怎么拼起来的

一份核心，多套壳。不是 IDE。

```text
┌──────────────────────────────────────────────┐
│ 壳：CLI / MCP / Vite / .app / .exe           │
└──────────────────┬───────────────────────────┘
                   │ CLI JSON 或 MCP stdio
┌──────────────────▼───────────────────────────┐
│ 核心：adapters → Snapshot v1 → HistoryStore  │
└──────────────────────────────────────────────┘
```

这是 Grok / Codex 的发行形态（runtime + 壳），不是 Cursor 的形态（VS Code 分叉）。
桌面 `.app` / `.exe` 包的是同一份 `continuum` CLI。不要为了 GUI 去 fork 编辑器。

契约、否决过的方案、失败导入该怎样，见 [docs/architecture.md](docs/architecture.md)。

## 参与开发

改行为之前先读 [CONTRIBUTING.md](CONTRIBUTING.md) 和 [docs/development.md](docs/development.md)。

```sh
uv sync --locked
uv run python scripts/check.py
```

门禁包括格式、lint、严格 mypy、测试（覆盖率门槛 85%）、基础发布卫生、wheel/sdist、隔离安装冒烟。
构建时可能出网拉依赖。它**不会**去读你的私人 Agent 历史。

请：

- 先写合成夹具和会失败的行为测试；
- 厂商库保持只读；
- 不要把真实 `state.vscdb`、日志、token 贴进 issue / PR；
- 不要靠删测试或降低覆盖率门槛把灯变绿。

CI 在 Ubuntu、macOS、Windows 上跑同一套门禁。

## 隐私

索引是明文。没有自动脱敏，也没有安全擦除保证。
只导入你愿意让所有连上该 `--db` 的客户端看到的内容。细节见 [SECURITY.md](SECURITY.md)。

## 常见问题

**为什么不能 `pip install continuum`？**
PyPI 上已有 [continuum](https://pypi.org/project/continuum/)，是 PyTorch 持续学习库。
本项目将来的发行名是 `continuum-history`。现在用 GitHub wheel 或源码。

**PyPI 上传为什么失败？**
GitHub OIDC 已经打到 PyPI（run `35454466719`），返回 422 `invalid-publisher`。
token 有效；pypi.org 上没有匹配 `continuum-history` / `bosprimigenious/continuum` /
`publish.yml` / environment `pypi` 的 pending publisher。
这是账号配置，不是版本号问题。步骤见 [docs/publishing.md](docs/publishing.md)。

**会不会把对话传到网上？**
运行时没有遥测、没有托管同步、没有模型 API。`uv` / `npm` / `cargo` 安装构建时仍会访问包仓库。

**接上 MCP 会不会把整库暴露出去？**
工具能读完**这一份**索引。要隔离就拆索引。宿主拿到正文之后做什么，不在 Continuum 里。

**能把 `--db` 指到 Cursor 自己的库吗？**
不能。`--db` 只给 Continuum 派生索引。厂商文件走 `import`。

**macOS `.app` 算正式版吗？**
不算。那是本机打包试验：未签名、未公证、也不从 GitHub Releases 分发。

## 许可

[MIT](LICENSE)。Copyright (c) 2026 Continuum contributors.

独立项目，与 Cursor、Anthropic、OpenAI 等厂商无隶属关系。名称不主张商标专用。
