import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import { AppRoutes } from "../App";
import { AuthProvider } from "../lib/auth";

type Handler = (body: unknown) => { status: number; body?: unknown };

export const unauthenticated = { status: 401, body: { error: { code: "not_authenticated", message: "Please sign in to continue." } } };

/**
 * Mock the API by "METHOD /path" (without the /api prefix). Unhandled calls fail the test.
 * Returns the spy so tests can assert on the requests made.
 */
export function mockApi(handlers: Record<string, Handler>) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = typeof input === "string" ? input : (input as Request).url;
    const key = `${init?.method ?? "GET"} ${url.replace(/^\/api/, "")}`;
    const handler = handlers[key];
    if (!handler) throw new Error(`Unexpected API call: ${key}`);
    const body = init?.body ? JSON.parse(init.body as string) : undefined;
    const result = handler(body);
    return new Response(result.body === undefined ? null : JSON.stringify(result.body), {
      status: result.status,
    });
  });
}

export function renderApp(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </MemoryRouter>,
  );
}
