import { describe, expect, it } from "vitest";

import { REFRESH_WINDOW_SECONDS, decodeExp, shouldRefresh } from "./tokenExpiry";

const DAY = 24 * 60 * 60;

function fakeJwt(claims: Record<string, unknown>): string {
  const b64url = (s: string) =>
    btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  return `${b64url('{"alg":"HS256","typ":"JWT"}')}.${b64url(JSON.stringify(claims))}.sig`;
}

describe("decodeExp", () => {
  it("reads the exp claim", () => {
    expect(decodeExp(fakeJwt({ sub: "5", exp: 1_800_000_000 }))).toBe(1_800_000_000);
  });

  it("handles base64url payloads that plain atob would reject", () => {
    // A payload whose base64 carries '+' and '/' and needs padding: the
    // previous helper in api.ts returned 0 for these and treated the token
    // as never expiring.
    const token = fakeJwt({ sub: "5", email: "a?b>c@example.com", exp: 1_700_000_001 });
    expect(token.includes("-") || token.includes("_")).toBe(true);
    expect(decodeExp(token)).toBe(1_700_000_001);
  });

  it("is 0 for garbage, a missing exp, or a non-numeric exp", () => {
    expect(decodeExp("")).toBe(0);
    expect(decodeExp("not.a.jwt")).toBe(0);
    expect(decodeExp(fakeJwt({ sub: "5" }))).toBe(0);
    expect(decodeExp(fakeJwt({ exp: "soon" }))).toBe(0);
  });
});

describe("shouldRefresh", () => {
  const now = 1_800_000_000;

  it("renews inside the last seven days and not before", () => {
    expect(shouldRefresh(now + 8 * DAY, now)).toBe(false);
    expect(shouldRefresh(now + REFRESH_WINDOW_SECONDS, now)).toBe(false);
    expect(shouldRefresh(now + REFRESH_WINDOW_SECONDS - 1, now)).toBe(true);
    expect(shouldRefresh(now + 1, now)).toBe(true);
  });

  it("still asks when the token already expired, so the backend gets to say no", () => {
    expect(shouldRefresh(now - 1, now)).toBe(true);
  });

  it("never renews an unreadable expiry", () => {
    expect(shouldRefresh(0, now)).toBe(false);
  });

  it("takes a custom window", () => {
    expect(shouldRefresh(now + 100, now, 50)).toBe(false);
    expect(shouldRefresh(now + 40, now, 50)).toBe(true);
  });
});
