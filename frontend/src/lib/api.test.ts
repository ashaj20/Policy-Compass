import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "./api";

afterEach(() => vi.restoreAllMocks());

describe("api", () => {
  it("turns the API error envelope into an ApiError", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({ error: { code: "permission_denied", message: "No access." } }),
        { status: 403 },
      ),
    );
    const err = (await api("/x").catch((e) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 403, code: "permission_denied", message: "No access." });
  });

  it("reports network failures in plain language", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("Failed to fetch"));
    const err = (await api("/x").catch((e) => e)) as ApiError;
    expect(err.code).toBe("network_error");
    expect(err.message).toMatch(/couldn't reach Policy Compass/);
  });
});
