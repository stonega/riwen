// Developer-test adapter for the production Python profile implementation.
import { resolve } from "node:path";

type Scheme = { id: string; name: string; correction: boolean };
async function command(args: string[]) {
  const child = Bun.spawn(
    ["python3", resolve(import.meta.dir, "../../scripts/runtime.py"), ...args],
    { stdout: "pipe", stderr: "pipe" },
  );
  const [output, errors, code] = await Promise.all([
    new Response(child.stdout).text(),
    new Response(child.stderr).text(),
    child.exited,
  ]);
  if (code !== 0) throw new Error(errors);
  return JSON.parse(output);
}
export async function discoverSchemes(
  source?: string,
): Promise<{ schemes: Scheme[]; selected: string }> {
  return command(["schemas", ...(source ? ["--source", source] : [])]);
}
export async function prepareProfile(
  target: string,
  port: number,
  source?: string,
  requested?: string,
): Promise<string> {
  return command([
    "profile",
    "--target",
    target,
    "--port",
    String(port),
    ...(source ? ["--source", source] : []),
    ...(requested ? ["--schema", requested] : []),
  ]);
}
