import { spawn } from "node:child_process";
import type { IncomingMessage, ServerResponse } from "node:http";
import type { Plugin } from "vite";

const ALLOWED = new Set(["import", "sources", "list", "search", "read"]);

type CliRequest = {
  db?: string;
  command?: string;
  args?: string[];
  proxy?: string;
};

export function continuumCliPlugin(repoRoot: string): Plugin {
  return {
    name: "continuum-cli",
    configureServer(server) {
      server.middlewares.use("/__continuum", (req, res, next) => {
        if (req.method !== "POST") {
          next();
          return;
        }
        collectBody(req)
          .then((body) => runCli(repoRoot, body, res))
          .catch((error: unknown) => {
            sendJson(res, 500, { error: error instanceof Error ? error.message : "cli_failed" });
          });
      });
    },
  };
}

function collectBody(req: IncomingMessage): Promise<CliRequest> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    req.on("data", (chunk: Buffer) => chunks.push(chunk));
    req.on("end", () => {
      const raw = Buffer.concat(chunks).toString("utf8");
      if (!raw.trim()) {
        resolve({});
        return;
      }
      try {
        resolve(JSON.parse(raw) as CliRequest);
      } catch {
        reject(new Error("cli_failed"));
      }
    });
    req.on("error", reject);
  });
}

function runCli(repoRoot: string, body: CliRequest, res: ServerResponse): void {
  const db = body.db?.trim() ?? "";
  const command = body.command?.trim() ?? "";
  const args = Array.isArray(body.args) ? body.args.map(String) : [];
  if (!db || !ALLOWED.has(command) || args.includes("serve")) {
    sendJson(res, 400, { error: "invalid_import: explicit db and allowed command required" });
    return;
  }
  const env = { ...process.env };
  const proxy = body.proxy?.trim() ?? "";
  if (proxy) {
    env.HTTPS_PROXY = proxy;
    env.https_proxy = proxy;
    env.HTTP_PROXY = proxy;
    env.http_proxy = proxy;
  }
  const child = spawn(
    "uv",
    ["run", "python", "-m", "continuum_history", "--db", db, "--format", "json", command, ...args],
    { cwd: repoRoot, env, shell: false },
  );
  let stdout = "";
  let stderr = "";
  child.stdout.setEncoding("utf8");
  child.stderr.setEncoding("utf8");
  child.stdout.on("data", (chunk: string) => {
    stdout += chunk;
  });
  child.stderr.on("data", (chunk: string) => {
    stderr += chunk;
  });
  child.on("error", (error) => {
    sendJson(res, 500, { error: error.message });
  });
  child.on("close", (code) => {
    if (code !== 0) {
      sendJson(res, 400, parseError(stderr));
      return;
    }
    sendJson(res, 200, stdout.trim() ? (JSON.parse(stdout) as unknown) : {});
  });
}

function parseError(stderr: string): { error: string } {
  try {
    const payload = JSON.parse(stderr) as { error?: string };
    if (payload.error) {
      return { error: payload.error };
    }
  } catch {
    /* CLI argparse text is not JSON; do not echo it. */
  }
  return { error: "cli_failed" };
}

function sendJson(res: ServerResponse, status: number, payload: unknown): void {
  if (res.writableEnded) {
    return;
  }
  res.statusCode = status;
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.end(JSON.stringify(payload));
}
