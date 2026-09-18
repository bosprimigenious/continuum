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

export function App() {
  const [db, setDb] = useState("");
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

  const state = error ? "error" : imported ? "ready" : "empty";

  async function call(
    command: "import" | "sources" | "list" | "search" | "read",
    args: string[] = [],
  ): Promise<CliPayload> {
    if (!db.trim()) {
      throw new Error("invalid_import: explicit db path required");
    }
    return runContinuum(db.trim(), command, args);
  }

  function clearResults() {
    setHits([]);
    setResultKind(null);
    setSearchCursor(null);
    setEvents([]);
    setActiveSession(null);
    setReadCursor(null);
  }

  async function onImport() {
    setBusy(true);
    setError(null);
    try {
      const args = [source.trim(), "--adapter", adapter];
      if (adapter === "cursor-state-vscdb") {
        args.push("--source-id", sourceId.trim());
      }
      await call("import", args);
      const listed = await call("sources");
      setSources(Array.isArray(listed.items) ? (listed.items as SourceRow[]) : []);
      setImported(true);
      clearResults();
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
      const args = [query, "--limit", "5"];
      if (append && searchCursor) {
        args.push("--cursor", searchCursor);
      }
      const result = await call("search", args);
      const page = Array.isArray(result.items) ? (result.items as ResultRow[]) : [];
      setResultKind("search");
      setHits((current) => (append ? [...current, ...page] : page));
      setSearchCursor(typeof result.next_cursor === "string" ? result.next_cursor : null);
      if (!append) {
        setEvents([]);
        setActiveSession(null);
        setReadCursor(null);
      }
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
      const args = ["--limit", "5"];
      if (append && searchCursor) {
        args.push("--cursor", searchCursor);
      }
      const result = await call("list", args);
      const page = Array.isArray(result.items) ? (result.items as ResultRow[]) : [];
      setResultKind("list");
      setHits((current) => (append ? [...current, ...page] : page));
      setSearchCursor(typeof result.next_cursor === "string" ? result.next_cursor : null);
      if (!append) {
        setEvents([]);
        setActiveSession(null);
        setReadCursor(null);
      }
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
      const args = [sessionId, "--limit", "2"];
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
      return "空态：尚未导入来源。";
    }
    if (state === "error" && error?.includes("stale_cursor")) {
      return "错误：索引已更新，请重新搜索或从头阅读。";
    }
    if (state === "error") {
      return `错误：${error}`;
    }
    return "已导入，可列表、搜索和阅读。";
  }

  return (
    <main className="page">
      <header>
        <h1>Continuum</h1>
        <p className="lede">
          通过 continuum CLI 导入、查看缺口、搜索并分页阅读。不扫描家目录，不另起一套检索。
        </p>
      </header>

      <section className="panel">
        <h2>来源</h2>
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
          <button type="button" disabled={busy || !db || !source} onClick={() => void onImport()}>
            导入
          </button>
          <button type="button" disabled={busy || !db || !source || !imported} onClick={() => void onImport()}>
            手动刷新
          </button>
        </div>
      </section>

      <p className={`status status-${state}`} data-state={state}>
        {statusText()}
      </p>

      {sources.length > 0 ? (
        <section className="panel">
          <h2>覆盖</h2>
          <ul className="sources">
            {sources.map((row) => {
              const coverage = row.coverage;
              const codes = (coverage?.issues ?? [])
                .map((issue) => issue.code)
                .filter(Boolean)
                .join(", ");
              const complete =
                coverage?.complete ?? coverage?.status === "supplied_snapshot";
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
      ) : null}

      <section className="panel">
        <h2>检索</h2>
        <form onSubmit={(event) => void onSearch(event)}>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="字面子串，例如 数据库锁"
            disabled={!imported}
          />
          <button type="submit" disabled={busy || !imported || !query.trim()}>
            搜索
          </button>
          <button type="button" disabled={busy || !imported} onClick={() => void onList(false)}>
            列出会话
          </button>
        </form>
        {imported && hits.length === 0 && !error ? <p>没有命中。</p> : null}
        <ul className="hits">
          {hits.map((hit, index) => {
            const sessionId = String(hit.session_id ?? hit.id ?? "");
            return (
              <li key={`${sessionId}-${hit.native_id ?? index}`}>
                <button type="button" onClick={() => void onRead(sessionId, null)}>
                  {hit.title ?? sessionId}
                </button>
                {hit.preview ? (
                  <p>
                    {hit.preview}
                    {hit.preview_truncated ? " （预览已截断，打开阅读看全文）" : ""}
                  </p>
                ) : null}
              </li>
            );
          })}
        </ul>
        {searchCursor ? (
          <button
            type="button"
            disabled={busy}
            onClick={() => void (resultKind === "list" ? onList(true) : fetchSearch(true))}
          >
            更多结果
          </button>
        ) : null}
      </section>

      <section className="panel">
        <h2>阅读</h2>
        {events.length === 0 ? <p>从列表或搜索结果打开一条会话。</p> : null}
        <ol className="events">
          {events.map((item) => (
            <li key={item.native_id}>
              <strong>{item.role}</strong>
              <pre>{item.text}</pre>
            </li>
          ))}
        </ol>
        {readCursor && activeSession ? (
          <button type="button" disabled={busy} onClick={() => void onRead(activeSession, readCursor)}>
            下一页
          </button>
        ) : null}
      </section>
    </main>
  );
}
