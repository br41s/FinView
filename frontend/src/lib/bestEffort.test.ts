import fs from "node:fs";
import path from "node:path";

import { afterEach, describe, expect, it, vi } from "vitest";

import { bestEffort } from "./bestEffort";

describe("bestEffort", () => {
  afterEach(() => vi.restoreAllMocks());

  it("swallows the rejection so the page keeps rendering", async () => {
    vi.spyOn(console, "warn").mockImplementation(() => {});

    await expect(
      Promise.reject(new Error("boom")).catch(bestEffort("a label")),
    ).resolves.toBeUndefined();
  });

  it("logs the label and the error so a persistent failure is findable", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const error = new Error("boom");

    await Promise.reject(error).catch(bestEffort("geo signal badges"));

    expect(warn).toHaveBeenCalledOnce();
    const [message, logged] = warn.mock.calls[0];
    expect(message).toContain("geo signal badges");
    expect(logged).toBe(error);
  });

  it("warns rather than errors — these are degradations, not failures", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const err = vi.spyOn(console, "error").mockImplementation(() => {});

    await Promise.reject(new Error("boom")).catch(bestEffort("x"));

    expect(warn).toHaveBeenCalled();
    expect(err).not.toHaveBeenCalled();
  });
});

/**
 * A bare `.catch(() => {})` leaves a persistent failure with no trace anywhere.
 * There were eleven; there should stay zero, because the next one gets written
 * by whoever is in a hurry.
 */
describe("no fetch swallows its error silently", () => {
  const SRC = path.join(process.cwd(), "src");
  const BARE_CATCH = /\.catch\(\s*\(\s*(?:_\w*)?\s*\)\s*=>\s*\{\s*\}\s*\)/;

  function sourceFiles(dir: string): string[] {
    return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) return sourceFiles(full);
      return /\.tsx?$/.test(entry.name) && !entry.name.endsWith(".test.ts") ? [full] : [];
    });
  }

  it("finds source files to check", () => {
    expect(sourceFiles(SRC).length).toBeGreaterThan(50);
  });

  it("has no bare .catch(() => {}) left", () => {
    const offenders = sourceFiles(SRC)
      .filter((file) => path.basename(file) !== "bestEffort.ts")
      .filter((file) => BARE_CATCH.test(fs.readFileSync(file, "utf8")))
      .map((file) => path.relative(SRC, file));

    expect(offenders, "use bestEffort(label) so the failure is at least logged").toEqual([]);
  });
});
