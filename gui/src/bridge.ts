export type CliPayload = Record<string, unknown>;

const ALLOWED = new Set(["import", "sources", "list", "search", "read"]);

function isTauri(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

function parseCliError(stderr: string): string {
  try {
    const payload = JSON.parse(stderr) as { error?: string };
    if (payload.error) {
      return String(payload.error);
    }
  } catch {
    /* CLI argparse text is not JSON; do not echo it. */
  }
  return "cli_failed";
}

async function runSidecar(
  db: string,
  command: string,
  args: string[],
): Promise<CliPayload> {
  const { Command } = await import("@tauri-apps/plugin-shell");
  const output = await Command.sidecar("binaries/continuum", [
    "--db",
    db,
    command,
    ...args,
  ]).execute();
  if (output.code !== 0) {
    throw new Error(parseCliError(output.stderr));
  }
  const stdout = output.stdout.trim();
  return stdout ? (JSON.parse(stdout) as CliPayload) : {};
}

async function runDevMiddleware(
  db: string,
  command: string,
  args: string[],
): Promise<CliPayload> {
  const response = await fetch("/__continuum", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ db, command, args }),
  });
  const payload = (await response.json()) as CliPayload;
  if (!response.ok) {
    throw new Error(String(payload.error ?? "cli_failed"));
  }
  return payload;
}

export async function runContinuum(
  db: string,
  command: "import" | "sources" | "list" | "search" | "read",
  args: string[] = [],
): Promise<CliPayload> {
  if (!db.trim() || !ALLOWED.has(command) || args.includes("serve")) {
    throw new Error("invalid_import: explicit db and allowed command required");
  }
  if (isTauri()) {
    return runSidecar(db.trim(), command, args);
  }
  return runDevMiddleware(db.trim(), command, args);
}
