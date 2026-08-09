import { describe, expect, it } from "vitest";
import { ClientMonitor, safeRoute, scrubPayload } from "../src";

describe("ClientMonitor safety", () => {
  it("rejects sensitive identity values", () => {
    expect(() => ClientMonitor.identify("person@example.com")).toThrow(/Sensitive/);
    expect(() => ClientMonitor.identify("+1 415 555 1234")).toThrow(/Sensitive/);
  });

  it("rejects invalid event names", () => {
    expect(() => ClientMonitor.track("<script>", {})).toThrow(/Invalid/);
  });

  it("redacts sensitive keys and token-like values", () => {
    expect(scrubPayload({
      lesson_id: "algebra-101",
      auth_token: "secret",
      nested: { email: "person@example.com" },
      typed: "person@example.com",
      opaque: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload.signature"
    })).toEqual({
      lesson_id: "algebra-101",
      auth_token: "[REDACTED]",
      nested: { email: "[REDACTED]" },
      typed: "[REDACTED]",
      opaque: "[REDACTED]"
    });
  });

  it("removes query strings from routes by default", () => {
    expect(safeRoute("/checkout?token=secret#step2")).toBe("/checkout#step2");
  });
});
