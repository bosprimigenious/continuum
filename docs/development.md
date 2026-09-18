# Development handbook

## Reproduce the foundation gate

```sh
uv sync --locked
uv run python scripts/check.py
```

Individual checks while iterating:

```sh
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest --cov --cov-report=term-missing
uv build
uv run python scripts/smoke_wheel.py
```

The wheel smoke uses an isolated environment and a temporary working directory. It verifies the
installed distribution can import the bundled repository's synthetic example and search it,
without importing the source checkout. Tests must never discover the developer's real history.

## 接续开发入口

项目类型是 **AI 开发工具 / 本地会话基础设施**，不是模型训练，也不是网站项目。
在本仓库根目录启动开发工具，不从旧聊天附件目录或用户主目录继续改代码。

接手时先运行 `git status --short`，保留未提交内容，再执行本文顶部的安装与聚合门禁。
以当前源码和亲自运行的结果为准，历史报告不替代复验。

接下来的开发请求应直接检查和修改代码，不要只输出计划（用户明确要求制订计划时除外）。
唯一当前里程碑是下文的 **一个 Cursor 原生只读路径**；合成适配器已经存在，
**P0 已在本工作区落地**（见 2026-09-18 证据）。下一刀是 **P1：贯通原生合成输入、stdio 和安装包**。
不要跳到 P5 GUI 或 Tauri。验收后再扩来源与 GUI。
发现竞品可以借鉴实现，
不因此自行推翻已确定范围、换技术栈或增加另一份产品设计稿。

- 先固定受支持的格式、版本与合成样本，写出因为行为缺失而失败的测试。
- 再实现适配器与共享服务接线；命中原文、完整分页、错误可见、重复采集幂等都要验证。
- 样本不覆盖的时间戳、分支、工具块和附件，明确记录缺口，不宣传全量支持。
- 必须保留外部数据库保护、游标范围/版本绑定、非 UTF-8 管道、跨平台元数据比较、
  源变化检测、事务回滚和 MCP 可恢复错误的回归测试。
- 真实本机日志只在用户明确授权范围内读取；不得进入仓库、公共 issue 或测试产物。
- 交付时列实际改动、Red/Green 证据、完整门禁结果、未运行的真实宿主与平台检查。
  原生链路未过就报 `native adapter NOT READY`，不能用基础测试通过替代。
- 不自动提交或推送；是否发布跟随当前用户请求。已有未提交规范也是待保留的工作。

首版以“找到并读完另一工具的已知会话”为终点，商业化、自动执行与云同步不属于这一步。
下文是这条里程碑的具体步骤和出口证据，不是另一条并行路线。

## Next milestone: one native Cursor path

Do not implement all sources or a desktop shell at once. Complete this one user path:
another developer installs from a checkout, explicitly selects a supported Cursor source,
finds a known conversation through MCP and reads to the end with correct references.

实施顺序和逐项出口见下文 P0–P3。P0 的合成失败边界已收紧；已有解析、CLI 和共享查询服务继续复用。
下一刀补原生合成输入贯通 stdio/wheel，再进入授权范围内的真实验收。

Exit evidence: fixture gate green; source unchanged by the reader; no silent omissions in
the supported fixture scope; long records readable to completion; known live record found;
independent install succeeds. Until these pass, say **native adapter NOT READY**.

### Locked Cursor format for this milestone

One observed IDE shape, not a vendor specification and not every Cursor store:

- **File:** explicitly selected SQLite `state.vscdb` (typical Cursor
  `User/globalStorage/state.vscdb` on macOS/Linux/Windows).
- **Table:** `cursorDiskKV(key, value)`.
- **Sessions:** `composerData:{composerId}` JSON (`_v`, `name`, `createdAt` ms,
  `fullConversationHeadersOnly`, optional `gitWorktree.worktreePath`).
- **Events:** `bubbleId:{composerId}:{bubbleId}` JSON (`type` 1=user / 2=assistant,
  optional `text`, optional `createdAt`).
- **Public observation window:** Cursor IDE 2.4–3.17 (2026). The database does not
  encode app version or OS; those stay `None` unless a later spike reads `product.json`.
- **Access:** `mode=ro` plus `query_only`; WAL sidecars are fingerprinted and not
  checkpointed. Repeating the same import is a no-op. `--source-id` is required.
- **Index schema:** derived Continuum indexes are `user_version=2`. Opening a v1
  foundation index fails closed. Rollback: keep the old file, create a **new** path,
  reimport retained snapshots/sources, verify counts, then point clients at the new
  index.

Supported fixture scope is header-ordered user/assistant text plus timestamps.
Tool results, thinking, code blocks, checkpoints, workspace sidebar DBs,
`composer.composerHeaders`, agent-transcripts JSONL and live host installs are
**gaps**: they must appear as coverage issues or remain unimplemented, never as
unparsed JSON stuffed into `Event.text`. JSONL trailing-record rules apply when
that later Cursor format is implemented.

Until a named live Cursor/OS combination and an independent install are recorded,
report **native adapter NOT READY** even if the synthetic fixture gate is green.

Then add Claude Code and Codex adapters individually, followed by the GUI search/read path.
An entire product is not finished just because a parser or screenshot works.

## 开发计划与当前证据（2026-09-17）

本次是计划维护，不实现下面的功能。推荐先完成 Cursor 的窄范围只读闭环：这是当前
风险最低的默认，也是后续多来源与 GUI 可复用的工程基础。现在引入通用插件框架、
后台常驻服务或桌面壳会扩大尚未验证的范围，没有必要。

### 基线与硬阻塞

检查对象是当前工作区，包含接手前已存在的未提交适配器、测试和文档；不是已发布版本。
亲自执行 `uv run python scripts/check.py`，本机 macOS / Python 3.12.13 的实际结果：

| 检查 | 实际输出 / 结论 |
| --- | --- |
| Ruff format / lint | `26 files already formatted` / `All checks passed!` |
| mypy | `Success: no issues found in 10 source files` |
| pytest | `56 passed`；总覆盖率 `91.32%`，门槛仍为 `85%` |
| 发布卫生检查 | `PASS: basic publication hygiene (35 files)` |
| wheel / sdist | 两种分发包构建成功 |
| 隔离 wheel 安装 | `PASS: installed wheel 0.1.0.dev0` |
| 聚合门禁 | `PASS: foundation gate (native adapters, GUI and real hosts are NOT verified)` |

隔离安装同时输出 `WARN --no-project was provided, but no project was found`，命令退出 0。
检查时误读了不存在的 `tests/test_mcp.py`，得到 `No such file or directory`；随后已读取
实际文件 `tests/test_interfaces.py`。这是检查路径错误，不是测试失败。

**当时状态：本机 foundation gate 通过；native adapter NOT READY；完整产品 NOT READY。**
当时不能被基础门禁通过掩盖的问题（前两项与 WAL/损坏覆盖已在 P0 关闭，见下节）：

- 临时合成库仅含 `_v=999`、标题、缺少 `fullConversationHeadersOnly` 的 composer 时，
  当时输出 `sessions_imported=1, events_imported=0, issues=(), complete=True`。
- 临时合成 composer 的 `createdAt=10**30` 时，当时抛出
  `OverflowError: timestamp out of range for platform time_t`。
- Cursor 合成链路测试使用进程内 MCP；实际 stdio 测试使用标准 snapshot。
  隔离 wheel 测试也只导入标准 snapshot，尚无一条原生输入贯通这两层的验收（仍是 P1）。
- 未运行真实 Cursor / MCP 宿主、非作者安装、当前工作区的 Linux / Windows CI。
  现有 CI 配置不等于此次远端运行结果。文中 Cursor 版本窗口是格式观察背景，
  不是已验证的应用版本兼容矩阵。

### P0 落地证据（2026-09-18）

工作区：`/Users/bosprimigenious/Projects/ai-tools/continuum`，macOS / Python 3.12.13。
未读取个人 Cursor 历史。GUI / Tauri 未开工（仍是 P5/P6）。

**Red（实现前，`uv run pytest tests/test_cursor_adapter.py tests/test_boundaries.py -q`）：**
`8 failed, 24 passed`。失败项对应手册已记录的缺口：缺失消息头被当成完整空会话、
`createdAt=10**30` 抛 `OverflowError`、未知 `_v` 仍 `complete=True`、超长 id 泄漏
Pydantic `ValidationError`、损坏采集覆盖旧索引、CLI 对未知形态返回 0、只读打开 WAL
源时 SHM 字节变化。

**Green（实现后同一命令）：** `32 passed in 0.81s`。

行为：

- 缺 `fullConversationHeadersOnly` → `unknown_shape`，不导入空会话，`complete=False`。
  显式 `fullConversationHeadersOnly: []` 仍是完整空会话。
- `createdAt=10**30` → `unusable_timestamp`，会话文本可导入，不抛裸 `OverflowError`。
- 未知 `_v` 且形状可解析 → `unrecognized_version`，导入已声明文本，`complete=False`。
- 超长 native id → `illegal_identity`（诊断里不含非法 id 原文）。
- 阻塞诊断（`unknown_shape` / `illegal_identity` / `malformed_record` / `missing_bubble` /
  `duplicate_event` / `invalid_composer`）使 `replace_source` 与 CLI 在写索引前失败：
  `incomplete_source`；revision、FTS、`indexed_at`、旧分页游标不变。CLI 对全新 `--db`
  不创建文件。stderr 不含源路径。
- 已知不支持的工具/思考块仍可导入，保留 `unsupported_block`。
- 直接 `mode=ro` 打开活跃 WAL 源会改 SHM 边车（已测到 index 104 处字节变化）。
  导入改为复制 main+WAL+SHM 到临时目录再读；源边车字节与 `journal_mode=wal` 保持不变。
  采集中途的真实 `COMMIT` 仍报 `source_changed`。

**聚合门禁** `uv run python scripts/check.py`（亲自跑）：

| 检查 | 实际输出 |
| --- | --- |
| Ruff format / lint | `26 files already formatted` / `All checks passed!` |
| mypy | `Success: no issues found in 10 source files` |
| pytest | `66 passed`；总覆盖率 `91.55%`，门槛仍为 `85%` |
| 发布卫生检查 | `PASS: basic publication hygiene (35 files)` |
| wheel / sdist | 构建成功 |
| 隔离 wheel 安装 | `PASS: installed wheel 0.1.0.dev0` |
| 聚合门禁 | `PASS: foundation gate (native adapters, GUI and real hosts are NOT verified)` |

未验证：真实 Cursor 宿主、stdio 原生合成贯通（P1）、非作者安装、Linux/Windows CI 远端结果。
回退：去掉本阶段代码后仍可读原有 v2 派生索引；新增诊断码不是 schema 迁移。

**状态：P0 合成失败边界已落地；native adapter NOT READY；GUI NOT READY；完整产品 NOT READY。**
下一刀是 P1，不是 P5。

### P0：收紧格式与失败边界（已落地，2026-09-18）

**输入 / 范围：** 当前 `cursor-state-vscdb`，只改 adapter、必要的 coverage 模型、
CLI 接线及对应测试；不增加来源、内容块模型或数据库迁移。

1. 在 `tests/test_cursor_adapter.py` 先补行为失败测试：缺失/错误类型的消息头、
   未知形态、超范围时间戳、非法记录标识。先记录 Red，不能仅补实现同构测试。
   区分合法的显式空会话与无法识别的记录；未知版本不能单凭数字推定兼容或不兼容。
2. 修改 `adapters/cursor_state_vscdb.py`：解析失败必须产生安全诊断或 `HistoryError`，
   不泄漏原始正文/路径、不抛裸异常；非支持形态不得声称完整。
   `complete` 明确只表示已声明的文本范围，不能等同于原生会话全部内容。
3. 固定失败导入策略：结构损坏、缺失被引用消息、源读取不稳定时默认不覆盖旧索引；
   已知不支持的工具/思考块可按现有文本范围导入，但必须保留缺口诊断。
   这是对当前可返回部分快照行为的收紧，目的是防止损坏采集清掉上一轮派生结果。
   在共享导入边界落实规则；此次不加隐式合并或 `--force` 绕过入口。
4. 用真实合成 SQLite 写入事务测试采集中变化、WAL 已提交记录与边车生命周期。
   当前主库字节比较和模拟变化测试继续保留；隔离观察读取本身是否改变边车。
   如果无法满足零源写入承诺，报告阻塞并评估一致性副本读取，不关闭检测掩盖问题。
5. 失败后断言已有索引的计数、正文、FTS、revision 与成功导入时间未变；
   成功重采集仍须 `changed=false`，且未变化的输入不使旧分页游标失效。

**命令：**

```sh
uv run pytest tests/test_cursor_adapter.py tests/test_boundaries.py -q
uv run python scripts/check.py
```

**出口：** 两个已复现问题有 Red/Green 证据；新失败路径安全且保留旧索引；WAL 行为
有可重复证据；完整聚合门禁通过。不得降低覆盖率门槛或删除其他数据库/分页/Unicode
回归。回退本阶段代码后仍能读取原有 v2 派生索引；新增诊断不冒充数据库迁移。

### P1：贯通原生合成输入、stdio 和安装包（依赖 P0）

**实施：** 扩展 `tests/test_interfaces.py` 和 `scripts/smoke_wheel.py`，复用合成构造器：
生成 Cursor SQLite → CLI 显式导入新索引 → 启动真实 stdio 子进程 → 四个 MCP 工具
查询 → 循环分页直到 `next_cursor=null`。至少包含中文搜索、40 条以上会话、末尾标记、
完整文本和 source_ref 身份校验；预期来自合成输入，不能只比较两个共用错误实现的接口。

隔离安装须通过已安装 wheel 的入口执行 Cursor 导入、幂等重导入及 stdio 查询；
不能从源码目录 import 核心来冒充安装成功。脚本可以在仓库侧生成合成输入文件，
运行时核心必须来自隔离环境的 `site-packages`。

```sh
uv run pytest tests/test_cursor_adapter.py tests/test_interfaces.py -q
uv run python scripts/check.py
```

**出口：** 原生合成长会话逐项匹配，原始源未被修改，错误和 coverage 经 MCP 可见；
聚合门禁包含这些用例。获得发布授权后，在候选提交上检查现有 Linux/macOS/Windows
CI 矩阵；没有远端证据的组合保留为未验证，不自动 push 触发 CI。

### P2：一个真实来源与一个真实 MCP 宿主（依赖 P1、显式授权）

**进入条件：** 用户明确选定可读取的源文件、允许核对的会话范围和消费它的 MCP
宿主；记录 Cursor 版本、OS、MCP 宿主版本和代码版本。优先用新建的非敏感验收会话。
本次制订计划不构成读取个人历史或更改客户端配置的授权。导入当前会读取所选库中的
全部受支持会话，不能把“允许看一条会话”扩张为“允许导入整个库”。

在已授权范围和专用新索引上执行，以下变量必须由执行者填入实际选择的值：

```sh
CURSOR_SOURCE='/absolute/path/to/selected/state.vscdb'
CONTINUUM_INDEX='/absolute/path/to/new/acceptance.sqlite3'
uv run continuum --db "$CONTINUUM_INDEX" import \
  --adapter cursor-state-vscdb --source-id cursor-acceptance "$CURSOR_SOURCE"
uv run continuum --db "$CONTINUUM_INDEX" sources
uv run continuum --db "$CONTINUUM_INDEX" search '约定的非敏感验收标记'
# 从上一步返回值复制 session_id
SESSION_ID='returned-session-id'
uv run continuum --db "$CONTINUUM_INDEX" read "$SESSION_ID" --limit 2
# 在另一终端或客户端配置中启动；客户端配置形状见 README
uv run continuum --db "$CONTINUUM_INDEX" serve
```

**核对：** 导入前后检查源及 WAL/SHM；宿主调用四个工具，找到已知首/中/末消息并读到
结尾；角色、顺序、正文和引用逐项对照授权源。重复导入无增量，无预期外缺口。
活动写入干扰时先报告 `source_changed`，不能通过删除边车或复制单个活动主库强行通过。
宿主可访问整个选定索引，项目过滤不是权限；暴露前确认索引范围符合授权。

**出口：** 一个具名来源版本 × OS × MCP 宿主组合通过；仅在本手册记脱敏版本、
数量、结果和缺口，不存会话正文、真实路径、原始数据库或客户端凭据。
失败则回到 P0/P1 补合成回归；无授权则 P2 保持 BLOCKED，不伪造真实验收。

### P3：非作者复装与首个原生里程碑验收（依赖 P2）

让未参与实现的人从候选 checkout 按 README 执行 `uv sync --locked` 和完整门禁，
再在其授权的源上完成“导入 → MCP 搜索 → 读到结尾”。记录安装命令、版本、失败步骤、
修复与重跑结果。自动 wheel smoke、实现者重装或第二个 agent 的报告不能替代这一步；
维护者仍需亲自复跑可以复现的命令。

**出口：** P0–P3 全部通过才允许称“该已记录组合的 Cursor 文本只读路径通过验收”。
仍不得称所有 Cursor 格式/平台受支持或完整产品 READY。同步中英文 README 的支持
范围，保留未实现项；提交、推送和发布由用户另行授权。

### 后续阶段（当前不启动）

| 顺序 / 依赖 | 有界交付 | 完成标准 |
| --- | --- | --- |
| P4a，P3 后 | Claude Code 的一种明确格式，只读显式导入；必要时将 coverage 从 Cursor 专用约束扩展到各适配器，保留旧快照兼容 | 自有合成契约、失败与幂等测试、安装包/stdio 链路、具名真实来源与宿主核对；不靠 Cursor 测试验收 |
| P4b，P4a 后 | Codex 的一种明确格式，同样复用 Snapshot / HistoryStore | 重走 P4a 门禁，并测试多来源相同文本不串身份、source/project 过滤和独立刷新 |
| P5，P4b 后 | React + TypeScript + Vite 的来源选择、覆盖状态、搜索和完整阅读页面；通过薄桥接层调用 Python 核心 | 用户选源 → 导入 → 看到失败/缺口 → 搜索 → 分页读原文 → 手动刷新；空态、错误恢复、过期游标和长中文内容均有端到端测试 |
| P6，P5 后 | Tauri 2 + Python sidecar 在一个目标平台的打包验证，再决定扩展平台 | 无开发环境的干净机器安装，核心启动/关闭无残留，搜索读取可用，升级失败可回到上一安装与索引；签名、分发和发布门禁单独验证 |

P5 首版用显式选择和手动全量快照刷新。自动发现只能在用户选择目录后提出候选；
后台增量更新等到实测全量刷新耗时/内存后再立项，不能因“以后会大”引入队列或守护进程。
GUI 桥接传输在 P5 小范围验证后写回 `docs/architecture.md`，不在这里预建另一套服务。
Cursor JSONL、内容块/附件、语义搜索、云同步、执行编排仍是独立后续需求。

### 迁移、回滚和每阶段交付

当前 normalized snapshot 版本仍为 1，派生 SQLite schema 为 2，两者不可混用。
P0/P1 默认不改数据库 schema；将来确需变更时，先在本手册记录字段变化、原因与旧版
读写边界，再添加旧版拒绝/新路径重建测试，不做未说明的原地 `ALTER`。

迁移顺序：停止读写客户端 → 为旧配置和派生索引制作一致性快照 → 保留旧文件及对应
可运行代码版本 → 指定全新索引路径重导入 → 核对 counts/coverage/搜索/末页 → 切换客户端。
失败时停止新客户端，恢复旧配置并用匹配版本打开旧索引。源文件始终不改、不删。
不能先切客户端再验证，否则失败的新索引会立即暴露；也不能在活跃 WAL 写入期间仅拷贝
主库当备份，否则已提交但尚未 checkpoint 的数据可能缺失。若需覆盖配置，先列变更清单
和备份；没有回滚副本就不执行覆盖。

每阶段交付都在本手册更新同一份证据，至少包含：代码版本/工作区状态、实际实现、
Red/Green 命令与退出码、完整门禁结果、失败/警告、已验证组合、未验证组合、回滚方法。
不以预计工期替代出口条件；P2 的用户授权和 P3 的独立验收是明确外部依赖。

## Contribution shape

```text
src/continuum_history/
  models.py          normalized input contract
  adapters/          bounded source readers
  store.py           transactions and shared query service
  cli.py             explicit import and local commands
  mcp_server.py      read-only protocol facade
tests/               synthetic contracts, faults, CLI and stdio integration
examples/            public synthetic data only
scripts/             aggregate gate and installed-wheel checks
```

Use the lockfile. Keep native-format interpretation in adapters and transport behavior in
facades. Do not copy local paths, credentials, raw user messages or personal agent instructions.

## Release checklist

- Run the aggregate gate on the commit being published; inspect its full output.
- Review `git diff --cached` and `git ls-files`; no real logs, databases or private paths.
- Verify CI on the supported foundation matrix; keep live/native checks separate.
- Ensure both READMEs describe implemented, planned and unverified capabilities accurately.
- Inspect the wheel/sdist contents. No native installer/PyPI release until its own gate exists.
- Follow [SECURITY.md](../SECURITY.md); automated hygiene checks are not a full secret audit.

Do not use screenshots, unit coverage or an agent's summary as substitutes for the real path.
