import { cp, mkdir, rm } from "node:fs/promises";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = fileURLToPath(new URL(".", import.meta.url));
const frontendRoot = resolve(here, "..");
const backendStatic = resolve(frontendRoot, "../backend/static");
const publicStatic = resolve(frontendRoot, "public/static");

await rm(publicStatic, { recursive: true, force: true });
await mkdir(publicStatic, { recursive: true });
await cp(resolve(backendStatic, "css"), resolve(publicStatic, "css"), { recursive: true });
await cp(resolve(backendStatic, "js"), resolve(publicStatic, "js"), { recursive: true });

console.log("Synced the proven LifeOS CSS/JS into React public/static.");
