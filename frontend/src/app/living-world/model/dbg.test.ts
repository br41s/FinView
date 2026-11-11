import { expect, it } from "vitest";
import { getCityGraph } from "./cityGraph";
import { buildLaneNetwork } from "./traffic";

// Scratch file left behind (agents may not delete files); safe to remove.
it("builds a lane network with controlled nodes", () => {
  const net = buildLaneNetwork(getCityGraph());
  expect(net.lanes.some((l) => l.control === "signal")).toBe(true);
});
