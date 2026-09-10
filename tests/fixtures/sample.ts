import def from "./mod-a";
import type { T } from "./types";
const cfg = require("mod-c");

/** Greet the user. */
export function greet(name: string): string {
  return "hi " + name;
}

export class Greeter {
  /** Greet doc. */
  greet(name: string): string {
    return name;
  }
}

const double = (x: number): number => x * 2;
const d = await import("./dyn");
