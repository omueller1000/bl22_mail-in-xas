import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "../test/render";
import { HomePage } from "./HomePage";

function respondWith(status: number, body: unknown) {
  const fetchMock = vi.fn<(request: Request) => Promise<Response>>(
    async () =>
      new Response(JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json" },
      }),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("HomePage system status", () => {
  it("shows server version and a healthy database", async () => {
    const fetchMock = respondWith(200, {
      status: "ok",
      database: "ok",
      environment: "local",
      version: "0.1.0",
    });

    renderWithProviders(<HomePage />);

    expect(await screen.findByText("v0.1.0 (local)")).toBeInTheDocument();
    expect(screen.getByText("ok")).toBeInTheDocument();
    // Vitest runs with base "/", the app with "/mail-in-xas/"; the API always sits below the base.
    const request = fetchMock.mock.calls[0]![0];
    expect(new URL(request.url).pathname).toBe(`${import.meta.env.BASE_URL}api/health`);
  });

  it("shows an unreachable database when the server reports 503", async () => {
    respondWith(503, {
      status: "degraded",
      database: "unreachable",
      environment: "local",
      version: "0.1.0",
    });

    renderWithProviders(<HomePage />);

    expect(await screen.findByText("unreachable")).toBeInTheDocument();
    expect(screen.getByText("v0.1.0 (local)")).toBeInTheDocument();
  });

  it("shows an unreachable server when the request fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      }),
    );

    renderWithProviders(<HomePage />);

    expect(await screen.findByText("unreachable")).toBeInTheDocument();
    expect(screen.getByText("Server")).toBeInTheDocument();
    expect(screen.queryByText("Database")).not.toBeInTheDocument();
  });
});
