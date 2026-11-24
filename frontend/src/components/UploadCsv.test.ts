import { createEvent, fireEvent, render, screen } from "@testing-library/svelte";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import UploadCsv from "./UploadCsv.svelte";

const NOT_CSV_MESSAGE = "Please upload a CSV file exported from Fidelity.";

function renderUpload(props: { loading?: boolean; error?: string | null } = {}) {
  const onUpload = vi.fn();
  render(UploadCsv, { props: { onUpload, loading: false, error: null, ...props } });
  return {
    onUpload,
    zone: screen.getByRole("button", { name: /drop your fidelity csv|parsing portfolio/i }),
    input: screen.getByLabelText("Fidelity CSV file") as HTMLInputElement,
  };
}

const csv = (name = "portfolio.csv") => new File(["a,b"], name, { type: "text/csv" });
const dropFiles = (zone: HTMLElement, files: File[]) =>
  fireEvent.drop(zone, { dataTransfer: { files } });

afterEach(() => vi.restoreAllMocks());

describe("UploadCsv", () => {
  it("renders the heading, Fidelity instructions and drop prompt", () => {
    renderUpload();
    expect(screen.getByRole("heading", { name: "Upload Portfolio" })).toBeInTheDocument();
    expect(screen.getByText("Accounts & Trade → Portfolio → Positions")).toBeInTheDocument();
    expect(screen.getByText("Download")).toBeInTheDocument();
    expect(screen.getByText("Drop your Fidelity CSV here, or click to browse")).toBeInTheDocument();
  });

  it("shows a parsing message instead of the drop prompt while loading", () => {
    renderUpload({ loading: true });
    expect(screen.getByText("Parsing portfolio…")).toBeInTheDocument();
    expect(screen.queryByText(/drop your fidelity csv/i)).not.toBeInTheDocument();
  });

  it("has a hidden file input restricted to CSVs", () => {
    const { input } = renderUpload();
    expect(input).toHaveAttribute("type", "file");
    expect(input).toHaveAttribute("accept", ".csv,text/csv");
    expect(input).not.toBeVisible();
  });

  it("opens the file picker when the drop zone is clicked", async () => {
    const clickSpy = vi.spyOn(HTMLInputElement.prototype, "click");
    const { zone } = renderUpload();
    await userEvent.setup().click(zone);
    expect(clickSpy).toHaveBeenCalledTimes(1);
  });

  it("calls onUpload with the file chosen through the input", async () => {
    const { onUpload, input } = renderUpload();
    const file = csv();
    await userEvent.setup().upload(input, file);
    expect(onUpload).toHaveBeenCalledTimes(1);
    expect(onUpload).toHaveBeenCalledWith(file);
  });

  it("does nothing when the file dialog is cancelled", async () => {
    const { onUpload, input } = renderUpload();
    await fireEvent.change(input, { target: { files: [] } });
    expect(onUpload).not.toHaveBeenCalled();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("accepts a file with a text/csv type even if the name is not .csv", async () => {
    const { onUpload, input } = renderUpload();
    const file = new File(["a,b"], "export.txt", { type: "text/csv" });
    await userEvent.setup({ applyAccept: false }).upload(input, file);
    expect(onUpload).toHaveBeenCalledWith(file);
  });

  it("accepts an uppercase .CSV extension", async () => {
    const { onUpload, input } = renderUpload();
    const file = new File(["a,b"], "PORTFOLIO.CSV", { type: "" });
    await userEvent.setup({ applyAccept: false }).upload(input, file);
    expect(onUpload).toHaveBeenCalledWith(file);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("rejects a non-CSV file chosen through the input with an inline alert", async () => {
    const alertSpy = vi.spyOn(window, "alert").mockImplementation(() => {});
    const { onUpload, input } = renderUpload();
    const file = new File(["hi"], "notes.txt", { type: "text/plain" });
    await userEvent.setup({ applyAccept: false }).upload(input, file);
    expect(onUpload).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent(NOT_CSV_MESSAGE);
    expect(alertSpy).not.toHaveBeenCalled();
  });

  describe("drag and drop", () => {
    it("toggles the drag-over class on dragover and dragleave", async () => {
      const { zone } = renderUpload();
      expect(zone).toHaveClass("drop-zone");
      expect(zone).not.toHaveClass("drag-over");

      await fireEvent.dragOver(zone);
      expect(zone).toHaveClass("drop-zone", "drag-over");

      await fireEvent.dragLeave(zone);
      expect(zone).toHaveClass("drop-zone");
      expect(zone).not.toHaveClass("drag-over");
    });

    it("prevents the default on dragover so dropping is allowed", () => {
      const { zone } = renderUpload();
      const event = createEvent.dragOver(zone);
      fireEvent(zone, event);
      expect(event.defaultPrevented).toBe(true);
    });

    it("calls onUpload with a dropped CSV and clears the drag-over state", async () => {
      const { onUpload, zone } = renderUpload();
      const file = csv();
      await fireEvent.dragOver(zone);
      await dropFiles(zone, [file]);
      expect(onUpload).toHaveBeenCalledTimes(1);
      expect(onUpload).toHaveBeenCalledWith(file);
      expect(zone).not.toHaveClass("drag-over");
    });

    it("accepts a dropped file with an uppercase .CSV extension", async () => {
      const { onUpload, zone } = renderUpload();
      const file = new File(["a,b"], "EXPORT.CSV", { type: "" });
      await dropFiles(zone, [file]);
      expect(onUpload).toHaveBeenCalledWith(file);
    });

    it.each([
      ["notes.txt", "text/plain"],
      ["chart.png", "image/png"],
    ])("rejects a dropped %s with an inline alert", async (name, type) => {
      const { onUpload, zone } = renderUpload();
      await dropFiles(zone, [new File(["x"], name, { type })]);
      expect(onUpload).not.toHaveBeenCalled();
      expect(screen.getByRole("alert")).toHaveTextContent(NOT_CSV_MESSAGE);
    });

    it("ignores a drop with no files", async () => {
      const { onUpload, zone } = renderUpload();
      await dropFiles(zone, []);
      expect(onUpload).not.toHaveBeenCalled();
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    });

    it("clears the rejection message once a valid CSV is dropped", async () => {
      const { onUpload, zone } = renderUpload();
      await dropFiles(zone, [new File(["x"], "notes.txt", { type: "text/plain" })]);
      expect(screen.getByRole("alert")).toBeInTheDocument();
      await dropFiles(zone, [csv()]);
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
      expect(onUpload).toHaveBeenCalledTimes(1);
    });
  });

  describe("error prop", () => {
    it("displays the error from the parent", () => {
      renderUpload({ error: "Could not parse file" });
      expect(screen.getByRole("alert")).toHaveTextContent("Could not parse file");
    });

    it("shows no alert when there is no error", () => {
      renderUpload();
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    });

    it("prefers the local rejection message over the parent error", async () => {
      const { zone } = renderUpload({ error: "Could not parse file" });
      await dropFiles(zone, [new File(["x"], "notes.txt", { type: "text/plain" })]);
      expect(screen.getAllByRole("alert")).toHaveLength(1);
      expect(screen.getByRole("alert")).toHaveTextContent(NOT_CSV_MESSAGE);
    });
  });
});
