import { resolve } from "node:path";
import { prepareProfile } from "./rime-profile";

const project = resolve(import.meta.dir, "..");
const profile = resolve(
  process.env.RIWEN_PROFILE ?? `${project}/.cache/ibus-profile`,
);
if (!profile.startsWith(`${project}/.cache/`))
  throw new Error("Experimental profile must be under the project's .cache");
const port = Number(process.env.RIWEN_PORT ?? 18765);
if (!Number.isInteger(port) || port < 1024 || port > 65535)
  throw new Error("Invalid RIWEN_PORT");
await prepareProfile(profile, port, process.env.RIWEN_RIME_SOURCE);
console.log(`Prepared isolated IBus profile: ${profile}`);
