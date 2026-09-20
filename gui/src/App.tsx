import { useState, type FormEvent } from "react";
import { runContinuum, type CliPayload } from "./bridge";

type CoverageIssue = { code?: string };
type SourceRow = {
  id?: string;
  adapter?: string;
  coverage?: { status?: string; complete?: boolean; issues?: CoverageIssue[] };
};
type ResultRow = {
  id?: string;
  session_id?: string;
  title?: string;
  preview?: string;
  preview_truncated?: boolean | number;
  role?: string;
  native_id?: string;
};
type ReadEvent = { native_id?: string; role?: string; text?: string };

const SETTINGS_KEY = "continuum.workbench.settings";
const PAGE = 20;

function readStoredSettings(): { db: string; proxy: string } {
  try {
    const raw = window.localStorage.getItem(SETTINGS_KEY);
    if (!raw) {
      return { db: "", proxy: "" };
    }
    const parsed = JSON.parse(raw) as { db?: unknown; proxy?: unknown };
    return {
      db: typeof parsed.db === "string" ? parsed.db : "",
      proxy: typeof parsed.proxy === "string" ? parsed.proxy : "",
    };
  } catch {
    return { db: "", proxy: "" };
  }
}

export function App() {
  const stored = readStoredSettings();
  const [db, setDb] = useState(stored.db);
  const [proxy, setProxy] = useState(stored.proxy);
  const [source, setSource] = useState("");
  const [adapter, setAdapter] = useState<"snapshot" | "cursor-state-vscdb">("snapshot");
  const [sourceId, setSourceId] = useState("");
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [imported, setImported] = useState(false);
  const [sources, setSources] = useState<SourceRow[]>([]);
  const [hits, setHits] = useState<ResultRow[]>([]);
  const [resultKind, setResultKind] = useState<"search" | "list" | null>(null);
  const [searchCursor, setSearchCursor] = useState<string | null>(null);
  const [activeSession, setActiveSession] = useState<string | null>(null);
  const [events, setEvents] = useState<ReadEvent[]>([]);
  const [readCursor, setReadCursor] = useState<string | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(!stored.db);
  const [coverageOpen, setCoverageOpen] = useState(false);

  const state = error ? "error" : imported ? "ready" : "empty";

  async function call(
    command: "import" | "sources" | "list" | "search" | "read",
    args: string[] = [],
  ): Promise<CliPayload> {
    if (!db.trim()) {
      throw new Error("invalid_import: explicit db path required");
    }
    return runContinuum(db.trim(), command, args, { proxy: proxy.trim() });
  }

  function persistSettings() {
    try {
      window.localStorage.setItem(SETTINGS_KEY, JSON.stringify({ db, proxy }));
    } catch {
      /* private mode; settings stay in memory */
    }
  }

  function applyHits(
    page: ResultRow[],
    kind: "search" | "list",
    next: string | null,
    append: boolean,
  ) {
    setResultKind(kind);
    setHits((current) => (append ? [...current, ...page] : page));
    setSearchCursor(next);
    if (!append) {
      setEvents([]);
      setActiveSession(null);
      setReadCursor(null);
    }
  }

  async function onImport() {
    setBusy(true);
    setError(null);
    persistSettings();
    try {
      const args = [source.trim(), "--adapter", adapter];
      if (adapter === "cursor-state-vscdb") {
        args.push("--source-id", sourceId.trim());
      }
      await call("import", args);
      const listed = await call("sources");
      setSources(Array.isArray(listed.items) ? (listed.items as SourceRow[]) : []);
      setImported(true);
      const sessions = await call("list", ["--limit", String(PAGE)]);
      const page = Array.isArray(sessions.items) ? (sessions.items as ResultRow[]) : [];
      applyHits(
        page,
        "list",
        typeof sessions.next_cursor === "string" ? sessions.next_cursor : null,
        false,
      );
      setSettingsOpen(false);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "cli_failed");
    } finally {
      setBusy(false);
    }
  }

  async function onSearch(event: FormEvent) {
    event.preventDefault();
    await fetchSearch(false);
  }

  async function fetchSearch(append: boolean) {
    setBusy(true);
    setError(null);
    try {
      const args = [query, "--limit", String(PAGE)];
      if (append && searchCursor) {
        args.push("--cursor", searchCursor);
      }
      const result = await call("search", args);
      const page = Array.isArray(result.items) ? (result.items as ResultRow[]) : [];
      applyHits(
        page,
        "search",
        typeof result.next_cursor === "string" ? result.next_cursor : null,
        append,
      );
    } catch (caught) {
      applyQueryError(caught);
    } finally {
      setBusy(false);
    }
  }

  async function onList(append: boolean) {
    setBusy(true);
    setError(null);
    try {
      const args = ["--limit", String(PAGE)];
      if (append && searchCursor) {
        args.push("--cursor", searchCursor);
      }
      const result = await call("list", args);
      const page = Array.isArray(result.items) ? (result.items as ResultRow[]) : [];
      applyHits(
        page,
        "list",
        typeof result.next_cursor === "string" ? result.next_cursor : null,
        append,
      );
    } catch (caught) {
      applyQueryError(caught);
    } finally {
      setBusy(false);
    }
  }

  async function onRead(sessionId: string, cursor: string | null) {
    setBusy(true);
    setError(null);
    try {
      const args = [sessionId, "--limit", String(PAGE)];
      if (cursor) {
        args.push("--cursor", cursor);
      }
      const result = await call("read", args);
      const page = Array.isArray(result.items) ? (result.items as ReadEvent[]) : [];
      setActiveSession(sessionId);
      setEvents((current) => (cursor ? [...current, ...page] : page));
      setReadCursor(typeof result.next_cursor === "string" ? result.next_cursor : null);
    } catch (caught) {
      applyQueryError(caught);
    } finally {
      setBusy(false);
    }
  }

  function applyQueryError(caught: unknown) {
    const message = caught instanceof Error ? caught.message : "cli_failed";
    setError(message);
    if (message.includes("stale_cursor")) {
      setSearchCursor(null);
      setReadCursor(null);
    }
  }

  function statusText(): string {
    if (state === "empty") {
      return "空态：在设置里填写索引路径并导入来源。";
    }
    if (state === "error" && error?.includes("stale_cursor")) {
      return "错误：索引已更新，请重新搜索或从头阅读。";
    }
    if (state === "error") {
      return `错误：${error}`;
    }
    return "已导入，可列表、搜索和阅读。";
  }

  const activeTitle =
    hits.find((hit) => String(hit.session_id ?? hit.id ?? "") === activeSession)?.title ??
    activeSession;

  return (
    <div
      className={coverageOpen ? "workbench coverage-open" : "workbench"}
      data-workbench="continuum"
    >
      <aside data-pane="navigator" className="pane pane-navigator">
        <div className="nav-brand">
          <img src="/favicon.png" width={28} height={28} alt="" />
          <div>
            <h1>Continuum</h1>
            <p className="lede">一份核心，CLI / MCP / 这扇窗口。</p>
          </div>
        </div>
        <div className="nav-actions">
          <button type="button" disabled={busy || !imported} onClick={() => void onList(false)}>
            全部会话
          </button>
        </div>
        {imported && hits.length === 0 && !error ? <p className="muted">没有命中。</p> : null}
        {!imported ? <p className="muted">导入之后这里列出会话。不扫描家目录。</p> : null}
        <ul className="hits">
          {hits.map((hit, index) => {
            const sessionId = String(hit.session_id ?? hit.id ?? "");
            const selected = sessionId === activeSession;
            return (
              <li key={`${sessionId}-${hit.native_id ?? index}`}>
                <button
                  type="button"
                  className={selected ? "hit selected" : "hit"}
                  onClick={() => void onRead(sessionId, null)}
                >
                  <span className="hit-title">{hit.title ?? sessionId}</span>
                  {hit.preview ? (
                    <span className="hit-preview">
                      {hit.preview}
                      {hit.preview_truncated ? " （预览已截断）" : ""}
                    </span>
                  ) : null}
                </button>
              </li>
            );
          })}
        </ul>
        {searchCursor ? (
          <button
            type="button"
            className="ghost more"
            disabled={busy}
            onClick={() => void (resultKind === "list" ? onList(true) : fetchSearch(true))}
          >
            更多结果
          </button>
        ) : null}
        <div className="nav-footer">
          <p className={`status status-${state}`} data-state={state}>
            {statusText()}
          </p>
          <div className="nav-footer-actions">
            <button
              type="button"
              className={coverageOpen ? "ghost active" : "ghost"}
              onClick={() => setCoverageOpen((open) => !open)}
            >
              覆盖
            </button>
            <button type="button" className="ghost" onClick={() => setSettingsOpen(true)}>
              设置
            </button>
          </div>
        </div>
      </aside>

      <section data-pane="transcript" className="pane pane-transcript">
        <header className="transcript-chrome">
          <h2>{activeTitle ? activeTitle : "阅读"}</h2>
        </header>
        <div className="transcript-scroll">
          {events.length === 0 ? (
            <div className="empty-transcript">
              <p>{imported ? "从左侧打开一条会话。" : "先在设置里导入来源，再搜索或打开会话。"}</p>
              <p className="muted">这里不是 diff，也不是 IDE。</p>
            </div>
          ) : null}
          <ol className="events">
            {events.map((item) => (
              <li key={item.native_id} className={`bubble role-${item.role ?? "unknown"}`}>
                <strong>{item.role}</strong>
                <pre>{item.text}</pre>
              </li>
            ))}
          </ol>
          {readCursor && activeSession ? (
            <button
              type="button"
              className="ghost"
              disabled={busy}
              onClick={() => void onRead(activeSession, readCursor)}
            >
              下一页
            </button>
          ) : null}
        </div>
        <form className="composer" onSubmit={(event) => void onSearch(event)}>
          <div className="composer-box">
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索已导入的对话，例如 数据库锁"
              disabled={!imported}
              spellCheck={false}
              autoComplete="off"
            />
            <button type="submit" disabled={busy || !imported || !query.trim()}>
              搜索
            </button>
          </div>
        </form>
      </section>

      <section
        data-pane="coverage"
        className="pane pane-coverage"
        hidden={!coverageOpen}
      >
        <h2>覆盖</h2>
        {sources.length === 0 ? <p className="muted">导入之后才有 coverage。不扫描家目录。</p> : null}
        <ul className="sources">
          {sources.map((row) => {
            const coverage = row.coverage;
            const codes = (coverage?.issues ?? [])
              .map((issue) => issue.code)
              .filter(Boolean)
              .join(", ");
            const complete = coverage?.complete ?? coverage?.status === "supplied_snapshot";
            return (
              <li key={String(row.id)}>
                <strong>{row.id}</strong>
                <p>
                  {coverage?.status ?? row.adapter} · complete={String(complete)}
                </p>
                {codes ? <p className="gaps">缺口：{codes}</p> : <p>没有列出的 coverage 缺口。</p>}
              </li>
            );
          })}
        </ul>
      </section>

      <section
        data-pane="settings"
        className={settingsOpen ? "pane pane-settings open" : "pane pane-settings"}
        hidden={!settingsOpen}
        onClick={() => setSettingsOpen(false)}
      >
        <div
          className="settings-card"
          onClick={(event) => {
            event.stopPropagation();
          }}
        >
          <div className="settings-head">
            <h2>设置</h2>
            <button type="button" className="ghost" onClick={() => setSettingsOpen(false)}>
              关闭
            </button>
          </div>
          <label>
            派生索引路径
            <input
              value={db}
              onChange={(event) => setDb(event.target.value)}
              spellCheck={false}
              autoComplete="off"
            />
          </label>
          <label>
            HTTPS_PROXY（可空，空则继承环境变量）
            <input
              value={proxy}
              onChange={(event) => setProxy(event.target.value)}
              spellCheck={false}
              autoComplete="off"
              placeholder="http://127.0.0.1:7890"
            />
          </label>
          <label>
            源文件路径
            <input
              value={source}
              onChange={(event) => setSource(event.target.value)}
              spellCheck={false}
              autoComplete="off"
            />
          </label>
          <label>
            适配器
            <select
              value={adapter}
              onChange={(event) =>
                setAdapter(event.target.value as "snapshot" | "cursor-state-vscdb")
              }
            >
              <option value="snapshot">snapshot</option>
              <option value="cursor-state-vscdb">cursor-state-vscdb</option>
            </select>
          </label>
          {adapter === "cursor-state-vscdb" ? (
            <label>
              source-id
              <input
                value={sourceId}
                onChange={(event) => setSourceId(event.target.value)}
                spellCheck={false}
                autoComplete="off"
              />
            </label>
          ) : null}
          <div className="actions">
            <button type="button" className="ghost" onClick={persistSettings}>
              保存设置
            </button>
            <button type="button" disabled={busy || !db || !source} onClick={() => void onImport()}>
              导入
            </button>
            <button
              type="button"
              disabled={busy || !db || !source || !imported}
              onClick={() => void onImport()}
            >
              手动刷新
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}
