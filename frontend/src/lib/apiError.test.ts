import { describe, expect, it } from "vitest";

import { apiError, errorFromBody } from "./apiError";

describe("errorFromBody", () => {
  it("unwraps a FastAPI detail string so the user sees the backend's own wording", () => {
    // The regression: this used to reach a toast as
    // `Import error: {"detail":"Solo se aceptan archivos PDF"}`.
    const err = errorFromBody('{"detail":"Solo se aceptan archivos PDF"}', 400);

    expect(err.message).toBe("Solo se aceptan archivos PDF");
  });

  it("joins the messages of a validation-error detail list", () => {
    const body = JSON.stringify({
      detail: [
        { loc: ["body", "email"], msg: "value is not a valid email address" },
        { loc: ["body", "password"], msg: "field required" },
      ],
    });

    expect(errorFromBody(body, 422).message).toBe(
      "value is not a valid email address; field required",
    );
  });

  it("falls back to the raw body when the response is plain text", () => {
    expect(errorFromBody("upstream request timeout", 504).message).toBe(
      "upstream request timeout",
    );
  });

  it("collapses an HTML error page to its status instead of showing markup", () => {
    expect(errorFromBody("<html>502 Bad Gateway</html>", 502).message).toBe("Error 502");
    expect(errorFromBody("<!DOCTYPE html><title>503</title>", 503).message).toBe("Error 503");
  });

  it("falls back to the status when the body is empty", () => {
    expect(errorFromBody("", 500).message).toBe("Error 500");
    expect(errorFromBody("   \n ", 503).message).toBe("Error 503");
  });

  it("ignores a detail that carries no usable text", () => {
    // A non-string, non-list detail must not become "[object Object]".
    expect(errorFromBody('{"detail":{"code":17}}', 400).message).toBe(
      '{"detail":{"code":17}}',
    );
    expect(errorFromBody('{"detail":""}', 400).message).toBe('{"detail":""}');
    expect(errorFromBody('{"detail":[]}', 400).message).toBe('{"detail":[]}');
  });

  it("trims surrounding whitespace from a detail string", () => {
    expect(errorFromBody('{"detail":"  Importación no encontrada  "}', 404).message).toBe(
      "Importación no encontrada",
    );
  });
});

describe("apiError", () => {
  it("reads the body off a Response", async () => {
    const res = new Response('{"detail":"Alert not found"}', { status: 404 });

    await expect(apiError(res)).resolves.toMatchObject({
      message: "Alert not found",
    });
  });
});
