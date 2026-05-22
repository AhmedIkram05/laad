import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { SearchProvider } from "../components/GlobalSearch";

describe("AnomalyListPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  async function renderList(props = {}) {
    const { default: AnomalyListPage } = await import("../components/AnomalyListPage");
    return render(
      <MemoryRouter>
        <SearchProvider>
          <AnomalyListPage title="Test Anomalies" subtitle="Test subtitle" isActive={1} {...props} />
        </SearchProvider>
      </MemoryRouter>
    );
  }

  it("renders title and subtitle", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ data: [] }),
    });

    await renderList();
    expect(screen.getByText("Test Anomalies")).toBeDefined();
    expect(screen.getByText("Test subtitle")).toBeDefined();
  });

  it("shows empty state when no anomalies", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ data: [], entities: [] }),
    });

    await renderList();

    const emptyMsg = await screen.findByText("No anomalies found.", {}, { timeout: 3000 });
    expect(emptyMsg).toBeDefined();
  }, 8000);

  it("has filter controls", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ data: [], entities: [] }),
    });

    await renderList();

    const sortEl = await screen.findByText("Sort:", {}, { timeout: 3000 });
    expect(sortEl).toBeDefined();
    expect(screen.getByText("Entity:")).toBeDefined();
    expect(screen.getByText("Anomaly:")).toBeDefined();
    expect(screen.getByText("Severity:")).toBeDefined();
    expect(screen.getByText("Detector:")).toBeDefined();
  }, 8000);
});
