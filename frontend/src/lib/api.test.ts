import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, uploadWithProgress } from "./api";

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

describe("uploadWithProgress", () => {
  class FakeXhr {
    static last: FakeXhr;
    status = 0;
    responseText = "";
    withCredentials = false;
    upload: { onprogress?: (e: { lengthComputable: boolean; loaded: number; total: number }) => void } = {};
    onload?: () => void;
    onerror?: () => void;
    url = "";
    constructor() {
      FakeXhr.last = this;
    }
    open(_method: string, url: string) {
      this.url = url;
    }
    send() {}
  }

  it("reports progress and resolves with the JSON body", async () => {
    vi.stubGlobal("XMLHttpRequest", FakeXhr);
    const progress: number[] = [];
    const promise = uploadWithProgress<{ id: string }>("/x", new FormData(), (p) => progress.push(p));
    const xhr = FakeXhr.last;
    expect(xhr.url).toBe("/api/x");
    expect(xhr.withCredentials).toBe(true);
    xhr.upload.onprogress?.({ lengthComputable: true, loaded: 63, total: 100 });
    xhr.status = 201;
    xhr.responseText = JSON.stringify({ id: "p1" });
    xhr.onload?.();
    await expect(promise).resolves.toEqual({ id: "p1" });
    expect(progress).toEqual([63]);
    vi.unstubAllGlobals();
  });

  it("rejects with the API's error message and fields", async () => {
    vi.stubGlobal("XMLHttpRequest", FakeXhr);
    const promise = uploadWithProgress("/x", new FormData(), () => {});
    const xhr = FakeXhr.last;
    xhr.status = 422;
    xhr.responseText = JSON.stringify({ error: { code: "invalid_file", message: "Bad file", fields: { file: "Bad file" } } });
    xhr.onload?.();
    await expect(promise).rejects.toMatchObject({ status: 422, code: "invalid_file", fields: { file: "Bad file" } });
    vi.unstubAllGlobals();
  });
});