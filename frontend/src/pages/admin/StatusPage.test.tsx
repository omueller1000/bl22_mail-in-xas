import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { formatBytes } from "../../materials/labels";
import { json, mockApi } from "../../test/mockApi";
import { renderWithProviders } from "../../test/render";
import { StatusPage } from "./StatusPage";

const NO_GROWTH = { sweeps: 0, bytes: 0, days_until_full: null as number | null };

function status(usedBytes: number, growth = NO_GROWTH) {
  return {
    version: "0.1.0",
    environment: "local",
    checked_at: "2026-10-16T10:00:00Z",
    database: {
      name: "ht_xas_dev",
      mongodb_version: "8.0.10",
      disk: { used_bytes: usedBytes, total_bytes: 1_000_000_000_000 },
      data_bytes: 2_000_000,
      storage_bytes: 1_500_000,
      index_bytes: 500_000,
      collections: [
        { name: "sweeps", documents: 25, data_bytes: 1_900_000, storage_bytes: 1_400_000, index_bytes: 200_000 },
        { name: "users", documents: 3, data_bytes: 1_000, storage_bytes: 36_864, index_bytes: 73_728 },
      ],
      growth: { days: 30, ...growth },
    },
  };
}

function setup(body: ReturnType<typeof status>) {
  mockApi({ "GET /admin/status": () => json(body) });
  renderWithProviders(<StatusPage />);
}

describe("StatusPage", () => {
  it("shows disk usage, the collections and the growth", async () => {
    setup(status(400_000_000_000, { sweeps: 120, bytes: 30_000_000_000, days_until_full: 600 }));
    expect(await screen.findByText(/400\.0 GB of 1\.00 TB used/)).toBeInTheDocument();
    expect(screen.getByText("600.0 GB free")).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: /40% used/ })).toBeInTheDocument();
    expect(screen.getByText(/takes 2\.00 MB of it/)).toBeInTheDocument();
    expect(screen.getByText(/120 sweeps uploaded, about 30\.0 GB/)).toBeInTheDocument();
    expect(screen.getByText(/full in about 600 days/)).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "sweeps" })).toBeInTheDocument();
    expect(screen.queryByText(/disk is \d+% full/)).not.toBeInTheDocument();
  });

  it("warns when the disk is nearly full", async () => {
    setup(status(920_000_000_000));
    expect(await screen.findByText(/MongoDB disk is 92% full/)).toBeInTheDocument();
    expect(screen.getByText(/No growth to estimate from/)).toBeInTheDocument();
  });

  it("does not forecast decades ahead", async () => {
    setup(status(400_000_000_000, { sweeps: 1, bytes: 1_000_000, days_until_full: 6_000_000 }));
    expect(await screen.findByText(/disk lasts more than 10 years/)).toBeInTheDocument();
  });
});

describe("formatBytes", () => {
  it("uses decimal units", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(1_500)).toBe("1.50 kB");
    expect(formatBytes(23_613_440)).toBe("23.6 MB");
    expect(formatBytes(5_495_416_946_688)).toBe("5.50 TB");
  });
});
