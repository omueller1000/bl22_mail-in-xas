import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { Sample } from "../api/client";
import { json, mockApi } from "../test/mockApi";
import { renderWithProviders } from "../test/render";
import { SamplesPage } from "./SamplesPage";

function sample(overrides: Partial<Sample>): Sample {
  return {
    id: "s1",
    name: "Fe2O3",
    description: "hematite",
    msds: null,
    archived: false,
    frozen: false,
    deletable: true,
    frames: [],
    data_frames: [],
    created_at: "2026-10-12T00:00:00Z",
    updated_at: "2026-10-12T00:00:00Z",
    ...overrides,
  };
}

async function openActions(name: string) {
  await userEvent.click(await screen.findByRole("button", { name: `Actions for ${name}` }));
}

describe("SamplesPage", () => {
  it("creates a sample", async () => {
    const fetchMock = mockApi({
      "GET /samples": () => json([]),
      "POST /samples": () => json(sample({}), 201),
    });
    renderWithProviders(<SamplesPage />);

    await userEvent.click(await screen.findByRole("button", { name: "New sample" }));
    await userEvent.type(screen.getByRole("textbox", { name: /Name/ }), " Fe2O3 ");
    await userEvent.type(screen.getByRole("textbox", { name: /Description/ }), "hematite");
    await userEvent.click(screen.getByRole("button", { name: "Create" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    const post = fetchMock.mock.calls.map(([r]) => r).find((r) => r.method === "POST")!;
    expect(await post.json()).toEqual({ name: "Fe2O3", description: "hematite" });
  });

  it("lists the sample's frames with links to the frame and its data", async () => {
    mockApi({
      "GET /samples": () =>
        json([
          sample({
            id: "s2",
            name: "CuO",
            frames: ["AAAA-AAAA", "BBBB-BBBB"],
            data_frames: ["BBBB-BBBB"],
          }),
        ]),
    });
    renderWithProviders(<SamplesPage />);
    expect(await screen.findByRole("link", { name: "AAAA-AAAA" })).toHaveAttribute(
      "href",
      "/frames/AAAA-AAAA",
    );
    expect(screen.getByRole("link", { name: "BBBB-BBBB" })).toHaveAttribute(
      "href",
      "/frames/BBBB-BBBB",
    );
    // A data icon only where this sample has data; it opens the viewer on the sample.
    expect(screen.queryByRole("link", { name: "Data of AAAA-AAAA" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Data of BBBB-BBBB" })).toHaveAttribute(
      "href",
      "/frames/BBBB-BBBB/data?sample=s2",
    );
  });

  it("filters the table by the search text", async () => {
    mockApi({
      "GET /samples": () =>
        json([
          sample({ id: "s1", name: "Fe2O3", description: "hematite" }),
          sample({ id: "s2", name: "CuO", description: "tenorite", frames: ["ABCD-EFGH"] }),
        ]),
    });
    renderWithProviders(<SamplesPage />);
    await screen.findByText("Fe2O3");
    const search = screen.getByRole("textbox", { name: "Search samples" });

    await userEvent.type(search, "HEMA"); // description, any case
    expect(screen.getByText("Fe2O3")).toBeInTheDocument();
    expect(screen.queryByText("CuO")).not.toBeInTheDocument();

    await userEvent.clear(search);
    await userEvent.type(search, "abcd-efgh"); // frame barcode
    expect(screen.getByText("CuO")).toBeInTheDocument();
    expect(screen.queryByText("Fe2O3")).not.toBeInTheDocument();

    await userEvent.type(search, "x");
    expect(screen.getByText("No sample matches “abcd-efghx”.")).toBeInTheDocument();
  });

  it("disables editing frozen samples and deleting undeletable ones", async () => {
    mockApi({
      "GET /samples": () =>
        json([sample({ frozen: true, deletable: false, frames: ["ABCD-EFGH"] })]),
    });
    renderWithProviders(<SamplesPage />);

    expect(await screen.findByLabelText("frozen")).toBeInTheDocument();
    expect(screen.getByText("ABCD-EFGH")).toBeInTheDocument();
    await openActions("Fe2O3");
    expect(await screen.findByRole("menuitem", { name: "Edit" })).toBeDisabled();
    expect(screen.getByRole("menuitem", { name: "Upload MSDS…" })).toBeDisabled();
    expect(screen.getByRole("menuitem", { name: "Delete…" })).toBeDisabled();
    expect(screen.getByRole("menuitem", { name: "Archive" })).toBeEnabled();
  });

  it("uploads an MSDS as a multipart file with the CSRF header", async () => {
    const fetchMock = mockApi({
      "GET /samples": () => json([sample({})]),
      "PUT /samples/s1/msds": () =>
        json(sample({ msds: { filename: "sds.pdf", size: 9, uploaded_at: "2026-10-12T00:00:00Z" } })),
    });
    const { container } = renderWithProviders(<SamplesPage />);
    await screen.findByText("Fe2O3");

    const input = container.ownerDocument.querySelector<HTMLInputElement>('input[type="file"]')!;
    await userEvent.upload(input, new File(["%PDF-1.4"], "sds.pdf", { type: "application/pdf" }));

    await waitFor(() => expect(fetchMock.mock.calls.some(([r]) => r.method === "PUT")).toBe(true));
    const put = fetchMock.mock.calls.map(([r]) => r).find((r) => r.method === "PUT")!;
    expect(put.headers.get("Content-Type")).toMatch(/^multipart\/form-data; boundary=/);
    expect(put.headers.get("X-Requested-With")).toBe("ht-xas");
    // Node's fetch turns jsdom's File into an anonymous blob, so only the field and type are
    // checked here; a real browser sends the file name and content.
    const body = await put.text();
    expect(body).toContain('name="file"');
    expect(body).toContain("Content-Type: application/pdf");
  });

  it("refuses MSDS files of 1 MB or more before uploading", async () => {
    const fetchMock = mockApi({ "GET /samples": () => json([sample({})]) });
    const { container } = renderWithProviders(<SamplesPage />);
    await screen.findByText("Fe2O3");

    const input = container.ownerDocument.querySelector<HTMLInputElement>('input[type="file"]')!;
    const big = new File([new Uint8Array(1024 * 1024 + 1)], "big.pdf", { type: "application/pdf" });
    await userEvent.upload(input, big);

    expect(await screen.findByText("The MSDS must be smaller than 1 MB")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([r]) => r.method === "PUT")).toBe(false);
  });
});
