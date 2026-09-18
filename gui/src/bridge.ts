export type CliPayload = Record<string, unknown>;

export async function runContinuum(
  db: string,
  command: "import" | "sources" | "list" | "search" | "read",
  args: string[] = [],
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
