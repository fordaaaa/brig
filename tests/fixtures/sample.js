import def from "mod-a";
import { x, y } from "mod-b";
const cfg = require("mod-c");

// leading comment for load
export async function load(url) {
  const d = await import("mod-d");
  function nested() {
    return 1;
  }
  return nested();
}

const double = (n) => n * 2;

class Foo extends Base {
  // method doc
  bar() {
    return 1;
  }
}
