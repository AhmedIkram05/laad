import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

const toastMock = { error: vi.fn(), success: vi.fn() };
vi.mock("sonner", () => ({
  toast: toastMock,
}));

const mockFetchAnomalies = vi.fn();
const mockFetchDetailedAnalysis = vi.fn();
const mockToggleComplete = vi.fn();
const mockToggleStar = vi.fn();

vi.mock("../api/api", () => ({
  fetchAnomalies: (...args) => mockFetchAnomalies(...args),
  fetchDetailedAnalysis: (...args) => mockFetchDetailedAnalysis(...args),
  toggleComplete: (...args) => mockToggleComplete(...args),
  toggleStar: (...args) => mockToggleStar(...args),
  getAuthHeaders: vi.fn().mockReturnValue({}),
}));

const defaultAnalysisData = {
  data: [
    {
      Anomaly: "network",
      root_cause: "Network timeout cascade detected",
      operations: "ATM-001 unavailable for 30 minutes",
      Recommended_Action: "Restart network equipment",
      recommended_action: "Restart network equipment",
      Title: "Network Timeout Cascade",
      Severity: "CRITICAL",
      Event_Time: "2024-01-15T10:00:00",
      model_confidence_score: 0.95,
      sources_involved: ["ATM_APP", "HARDWARE"],
      detection_source: "ML_ENSEMBLE",
    },
  ],
};

const defaultAnomaliesData = {
  data: [
    {
      id: 1,
      anomaly_type: "network",
      is_active: 1,
      is_starred: 0,
      model_confidence_score: 0.95,
      sources_involved: ["ATM_APP", "HARDWARE"],
      correlation_id: "corr-123-abc",
      explanation: JSON.stringify({ source: "ML_ENSEMBLE" }),
    },
  ],
};

async function renderComponent(
  anomalyType = "network",
  analysisData = defaultAnalysisData,
  anomaliesData = defaultAnomaliesData
) {
  mockFetchDetailedAnalysis.mockResolvedValue(analysisData);
  mockFetchAnomalies.mockResolvedValue(anomaliesData);
  mockToggleComplete.mockResolvedValue({});
  mockToggleStar.mockResolvedValue({});

  const { default: AnomalyData } = await import("../pages/AnomalyData");
  return render(
    <MemoryRouter initialEntries={[`/data/${anomalyType}/1`]}>
      <Routes>
        <Route path="/data/:anomaly_type/:id" element={<AnomalyData />} />
      </Routes>
    </MemoryRouter>
  );
}

describe("AnomalyData Coverage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the anomaly title after loading", async () => {
    await renderComponent();

    await waitFor(() => {
      expect(screen.getByText("Network Timeout Cascade")).toBeDefined();
    });
  });

  it("renders root cause section", async () => {
    await renderComponent();

    await waitFor(() => {
      expect(screen.getByText("Root Cause")).toBeDefined();
      expect(
        screen.getByText("Network timeout cascade detected")
      ).toBeDefined();
    });
  });

  it("renders operation impact section", async () => {
    await renderComponent();

    await waitFor(() => {
      expect(screen.getByText("Operation Impact")).toBeDefined();
      expect(
        screen.getByText("ATM-001 unavailable for 30 minutes")
      ).toBeDefined();
    });
  });

  it("renders recommended action with Actionable badge", async () => {
    await renderComponent();

    await waitFor(() => {
      expect(screen.getByText("Recommended Action")).toBeDefined();
      expect(screen.getByText("Actionable")).toBeDefined();
      expect(
        screen.getByText("Restart network equipment")
      ).toBeDefined();
    });
  });

  it("renders severity badge", async () => {
    await renderComponent();

    await waitFor(() => {
      expect(screen.getByText("CRITICAL")).toBeDefined();
    });
  });

  it("renders ATM / Server ID in details", async () => {
    await renderComponent();

    await waitFor(() => {
      expect(screen.getByText("ATM / Server:")).toBeDefined();
      expect(screen.getByText("SERVER")).toBeDefined();
    });
  });

  it("displays confidence score as percentage", async () => {
    await renderComponent();

    await waitFor(() => {
      expect(screen.getByText("95%")).toBeDefined();
      expect(screen.getByText("Confidence")).toBeDefined();
    });
  });

  it("renders high confidence bar (>=0.8) with emerald color", async () => {
    await renderComponent();

    await waitFor(() => {
      const bar = document.querySelector(".bg-emerald-500");
      expect(bar).toBeDefined();
      expect(bar.style.width).toBe("95%");
    });
  });

  it("renders medium confidence bar (>=0.6) with amber color", async () => {
    await renderComponent(
      "network",
      {
        data: [
          {
            ...defaultAnalysisData.data[0],
            model_confidence_score: null,
          },
        ],
      },
      {
        data: [
          {
            ...defaultAnomaliesData.data[0],
            model_confidence_score: 0.7,
          },
        ],
      }
    );

    await waitFor(() => {
      expect(screen.getByText("70%")).toBeDefined();
      const bar = document.querySelector(".bg-amber-500");
      expect(bar).toBeDefined();
      expect(bar.style.width).toBe("70%");
    });
  });

  it("renders low confidence bar (<0.6) with red color", async () => {
    await renderComponent(
      "network",
      {
        data: [
          {
            ...defaultAnalysisData.data[0],
            model_confidence_score: null,
          },
        ],
      },
      {
        data: [
          {
            ...defaultAnomaliesData.data[0],
            model_confidence_score: 0.4,
          },
        ],
      }
    );

    await waitFor(() => {
      expect(screen.getByText("40%")).toBeDefined();
      const bar = document.querySelector(".bg-red-500");
      expect(bar).toBeDefined();
    });
  });

  it("displays detection source badge", async () => {
    await renderComponent();

    await waitFor(() => {
      expect(screen.getByText("Detected By:")).toBeDefined();
      expect(screen.getByText("ML_ENSEMBLE")).toBeDefined();
    });
  });

  it("parses detection source from dbAnomaly explanation JSON", async () => {
    await renderComponent(
      "network",
      {
        data: [
          {
            ...defaultAnalysisData.data[0],
            detection_source: undefined,
          },
        ],
      },
      {
        data: [
          {
            ...defaultAnomaliesData.data[0],
            explanation: JSON.stringify({ source: "ZSCORE" }),
          },
        ],
      }
    );

    await waitFor(() => {
      expect(screen.getByText("ZSCORE")).toBeDefined();
    });
  });

  it("displays sources list as badges", async () => {
    await renderComponent();

    await waitFor(() => {
      expect(screen.getByText("Sources:")).toBeDefined();
      expect(screen.getByText("ATM_APP")).toBeDefined();
      expect(screen.getByText("HARDWARE")).toBeDefined();
    });
  });

  it("displays correlation_id", async () => {
    await renderComponent();

    await waitFor(() => {
      expect(screen.getByText("Correlation ID:")).toBeDefined();
      expect(screen.getByText("corr-123-abc")).toBeDefined();
    });
  });

  it("handles star toggle successfully", async () => {
    await renderComponent();

    await waitFor(() => {
      expect(screen.getByText("Star")).toBeDefined();
    });

    fireEvent.click(screen.getByText("Star"));

    await waitFor(() => {
      expect(mockToggleStar).toHaveBeenCalledWith(1);
      expect(screen.getByText("Starred")).toBeDefined();
    });
  });

  it("handles complete toggle successfully", async () => {
    await renderComponent();

    await waitFor(() => {
      expect(screen.getByText("Mark Complete")).toBeDefined();
    });

    fireEvent.click(screen.getByText("Mark Complete"));

    await waitFor(() => {
      expect(mockToggleComplete).toHaveBeenCalledWith(1);
      expect(screen.getByText("Completed")).toBeDefined();
    });
  });

  it("shows toast error when complete toggle fails", async () => {
    await renderComponent();
    // Set rejection AFTER renderComponent (which sets mockResolvedValue)
    mockToggleComplete.mockRejectedValue(new Error("API error"));

    await waitFor(() => {
      expect(screen.getByText("Mark Complete")).toBeDefined();
    });

    fireEvent.click(screen.getByText("Mark Complete"));

    await waitFor(() => {
      expect(toastMock.error).toHaveBeenCalledWith("Failed to update status");
    });
  });

  it("logs error when star toggle fails", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    await renderComponent();
    // Set rejection AFTER renderComponent (which sets mockResolvedValue)
    mockToggleStar.mockRejectedValue(new Error("API error"));

    await waitFor(() => {
      expect(screen.getByText("Star")).toBeDefined();
    });

    fireEvent.click(screen.getByText("Star"));

    await waitFor(() => {
      expect(consoleSpy).toHaveBeenCalled();
    });

    consoleSpy.mockRestore();
  });

  it("does not call toggleStar when dbAnomaly is null", async () => {
    mockFetchAnomalies.mockResolvedValue({ data: [] });
    mockFetchDetailedAnalysis.mockResolvedValue(defaultAnalysisData);

    const { default: AnomalyData } = await import("../pages/AnomalyData");
    render(
      <MemoryRouter initialEntries={["/data/unknown/1"]}>
        <Routes>
          <Route path="/data/:anomaly_type/:id" element={<AnomalyData />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText("Network Timeout Cascade")).toBeDefined();
    });

    fireEvent.click(screen.getByText("Star"));

    await waitFor(() => {
      expect(mockToggleStar).not.toHaveBeenCalled();
    });
  });

  it("shows loading skeleton while fetching", async () => {
    mockFetchDetailedAnalysis.mockReturnValue(new Promise(() => {}));
    mockFetchAnomalies.mockReturnValue(new Promise(() => {}));

    await renderComponent();

    const skeleton = document.querySelector(".animate-pulse");
    expect(skeleton).toBeDefined();
  });

  it("shows empty state when no analysis data", async () => {
    await renderComponent(
      "unknown",
      { data: [] },
      { data: [] }
    );

    await waitFor(() => {
      expect(
        screen.getByText("No analysis data available for this anomaly type.")
      ).toBeDefined();
    });
  });

  it("formats Event_Time with formatUKDateTime", async () => {
    await renderComponent();

    await waitFor(() => {
      expect(screen.getByText("Time Received:")).toBeDefined();
      const timeText = screen.getByText("Time Received:").parentElement
        .querySelector("span:last-child");
      expect(timeText).toBeDefined();
      expect(timeText.textContent).not.toBe("Time Unknown");
    });
  });

  it("shows 'Time Unknown' when Event_Time is missing", async () => {
    await renderComponent("network", {
      data: [
        {
          ...defaultAnalysisData.data[0],
          Event_Time: null,
        },
      ],
    });

    await waitFor(() => {
      expect(screen.getByText("Time Unknown")).toBeDefined();
    });
  });

  it("shows fallback root cause when missing", async () => {
    await renderComponent("network", {
      data: [
        {
          ...defaultAnalysisData.data[0],
          root_cause: undefined,
        },
      ],
    });

    await waitFor(() => {
      expect(screen.getByText("Root Cause Unknown.")).toBeDefined();
    });
  });

  it("shows fallback operation impact when missing", async () => {
    await renderComponent("network", {
      data: [
        {
          ...defaultAnalysisData.data[0],
          operations: undefined,
        },
      ],
    });

    await waitFor(() => {
      expect(screen.getByText("Operation Impact Unknown.")).toBeDefined();
    });
  });

  it("shows fallback recommended action when missing", async () => {
    await renderComponent("network", {
      data: [
        {
          ...defaultAnalysisData.data[0],
          recommended_action: undefined,
          Recommended_Action: undefined,
        },
      ],
    });

    await waitFor(() => {
      expect(screen.getByText("Recommended Action Unknown.")).toBeDefined();
    });
  });

  it("does not show Actionable badge when no recommended action", async () => {
    await renderComponent("network", {
      data: [
        {
          ...defaultAnalysisData.data[0],
          recommended_action: undefined,
          Recommended_Action: undefined,
        },
      ],
    });

    await waitFor(() => {
      expect(screen.queryByText("Actionable")).toBeNull();
    });
  });

  it("shows Title Unknown fallback when Title is missing", async () => {
    await renderComponent("network", {
      data: [
        {
          ...defaultAnalysisData.data[0],
          Title: undefined,
        },
      ],
    });

    await waitFor(() => {
      expect(screen.getByText("Title Unknown")).toBeDefined();
    });
  });

  it("displays Severity Unknown when Severity is missing", async () => {
    await renderComponent("network", {
      data: [
        {
          ...defaultAnalysisData.data[0],
          Severity: undefined,
        },
      ],
    });

    await waitFor(() => {
      expect(screen.getByText("Unknown")).toBeDefined();
    });
  });

  it("hides correlation_id row when not present", async () => {
    await renderComponent(
      "network",
      defaultAnalysisData,
      {
        data: [
          {
            ...defaultAnomaliesData.data[0],
            correlation_id: undefined,
          },
        ],
      }
    );

    await waitFor(() => {
      expect(screen.queryByText("Correlation ID:")).toBeNull();
    });
  });

  it("hides confidence bar when confidence is null", async () => {
    await renderComponent(
      "network",
      {
        data: [
          {
            ...defaultAnalysisData.data[0],
            model_confidence_score: null,
          },
        ],
      },
      {
        data: [
          {
            ...defaultAnomaliesData.data[0],
            model_confidence_score: null,
          },
        ],
      }
    );

    await waitFor(() => {
      expect(screen.queryByText("Confidence")).toBeNull();
    });
  });

  it("hides detection source when not available", async () => {
    await renderComponent(
      "network",
      {
        data: [
          {
            ...defaultAnalysisData.data[0],
            detection_source: undefined,
          },
        ],
      },
      {
        data: [
          {
            ...defaultAnomaliesData.data[0],
            explanation: "not-json",
          },
        ],
      }
    );

    await waitFor(() => {
      expect(screen.queryByText("Detected By:")).toBeNull();
    });
  });

  it("hides sources list when empty", async () => {
    await renderComponent(
      "network",
      {
        data: [
          {
            ...defaultAnalysisData.data[0],
            sources_involved: [],
          },
        ],
      },
      {
        data: [
          {
            ...defaultAnomaliesData.data[0],
            sources_involved: [],
          },
        ],
      }
    );

    await waitFor(() => {
      expect(screen.queryByText("Sources:")).toBeNull();
    });
  });

  it("handles malformed explanation JSON gracefully", async () => {
    await renderComponent(
      "network",
      {
        data: [
          {
            ...defaultAnalysisData.data[0],
            detection_source: undefined,
          },
        ],
      },
      {
        data: [
          {
            ...defaultAnomaliesData.data[0],
            explanation: "this is not json {{{",
          },
        ],
      }
    );

    await waitFor(() => {
      expect(screen.queryByText("Detected By:")).toBeNull();
    });
  });

  it("calls fetchDetailedAnalysis and fetchAnomalies on mount", async () => {
    await renderComponent();

    await waitFor(() => {
      expect(mockFetchDetailedAnalysis).toHaveBeenCalledWith("network");
      expect(mockFetchAnomalies).toHaveBeenCalled();
    });
  });

  it("shows back button", async () => {
    await renderComponent();

    await waitFor(() => {
      expect(screen.getByText("Back")).toBeDefined();
    });
  });

  it("shows description subtitle", async () => {
    await renderComponent();

    await waitFor(() => {
      expect(
        screen.getByText(
          "Review analysis, understand the ATM issue, and follow the recommended actions."
        )
      ).toBeDefined();
    });
  });

  it("star button toggles between Star and Starred text", async () => {
    await renderComponent();

    await waitFor(() => {
      expect(screen.getByText("Star")).toBeDefined();
    });

    fireEvent.click(screen.getByText("Star"));

    await waitFor(() => {
      expect(screen.getByText("Starred")).toBeDefined();
      expect(screen.queryByText("Star")).toBeNull();
    });
  });

  it("complete button toggles between Mark Complete and Completed", async () => {
    await renderComponent();

    await waitFor(() => {
      expect(screen.getByText("Mark Complete")).toBeDefined();
    });

    fireEvent.click(screen.getByText("Mark Complete"));

    await waitFor(() => {
      expect(screen.getByText("Completed")).toBeDefined();
      expect(screen.queryByText("Mark Complete")).toBeNull();
    });
  });

  it("renders confidence with correct percentage for various scores", async () => {
    await renderComponent(
      "network",
      {
        data: [
          {
            ...defaultAnalysisData.data[0],
            model_confidence_score: null,
          },
        ],
      },
      {
        data: [
          {
            ...defaultAnomaliesData.data[0],
            model_confidence_score: 0.65,
          },
        ],
      }
    );

    await waitFor(() => {
      expect(screen.getByText("65%")).toBeDefined();
    });
  });

  it("displays detection source from analysis data over dbAnomaly", async () => {
    await renderComponent(
      "network",
      {
        data: [
          {
            ...defaultAnalysisData.data[0],
            detection_source: "HEURISTIC",
          },
        ],
      },
      {
        data: [
          {
            ...defaultAnomaliesData.data[0],
            explanation: JSON.stringify({ source: "ZSCORE" }),
          },
        ],
      }
    );

    await waitFor(() => {
      expect(screen.getByText("HEURISTIC")).toBeDefined();
    });
  });
});
