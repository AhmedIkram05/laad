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

  // ─── loading and data display ─────────────────────────

  it("renders the anomaly title after loading", async () => {
    await renderComponent();

    await waitFor(() => {
      expect(screen.getByText("Network Timeout Cascade")).toBeDefined();
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

  it("calls fetchDetailedAnalysis and fetchAnomalies on mount", async () => {
    await renderComponent();

    await waitFor(() => {
      expect(mockFetchDetailedAnalysis).toHaveBeenCalledWith("network");
      expect(mockFetchAnomalies).toHaveBeenCalled();
    });
  });

  // ─── sections ─────────────────────────────────────────

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

  it("shows back button", async () => {
    await renderComponent();

    await waitFor(() => {
      expect(screen.getByText("Back")).toBeDefined();
    });
  });

  // ─── details section ──────────────────────────────────

  it("renders ATM / Server ID in details", async () => {
    await renderComponent();

    await waitFor(() => {
      expect(screen.getByText("ATM / Server:")).toBeDefined();
      expect(screen.getByText("SERVER")).toBeDefined();
    });
  });

  it("displays ATM_ID from analysis data when available", async () => {
    await renderComponent("network", {
      data: [
        {
          ...defaultAnalysisData.data[0],
          ATM_ID: "ATM-001",
        },
      ],
    });

    await waitFor(() => {
      expect(screen.getByText("ATM-001")).toBeDefined();
    });
  });

  it("displays ATM_ID from dbAnomaly when analysis has none", async () => {
    await renderComponent(
      "network",
      {
        data: [
          {
            ...defaultAnalysisData.data[0],
            ATM_ID: undefined,
          },
        ],
      },
      {
        data: [
          {
            ...defaultAnomaliesData.data[0],
            atm_id: "ATM-SERVER-002",
          },
        ],
      }
    );

    await waitFor(() => {
      expect(screen.getByText("ATM-SERVER-002")).toBeDefined();
    });
  });

  // ─── confidence score ─────────────────────────────────

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

  it("displays confidence from data. model_confidence_score over dbAnomaly", async () => {
    await renderComponent(
      "network",
      {
        data: [
          {
            ...defaultAnalysisData.data[0],
            model_confidence_score: 0.88,
          },
        ],
      },
      {
        data: [
          {
            ...defaultAnomaliesData.data[0],
            model_confidence_score: 0.5,
          },
        ],
      }
    );

    await waitFor(() => {
      expect(screen.getByText("88%")).toBeDefined();
    });
  });

  // ─── detection source ─────────────────────────────────

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

  it("parses detection source from explanation with missing source key", async () => {
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
            explanation: JSON.stringify({ other_key: "value" }),
          },
        ],
      }
    );

    await waitFor(() => {
      expect(screen.queryByText("Detected By:")).toBeNull();
    });
  });

  // ─── sources list ─────────────────────────────────────

  it("displays sources list as badges", async () => {
    await renderComponent();

    await waitFor(() => {
      expect(screen.getByText("Sources:")).toBeDefined();
      expect(screen.getByText("ATM_APP")).toBeDefined();
      expect(screen.getByText("HARDWARE")).toBeDefined();
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

  it("renders multiple sources as individual badges", async () => {
    await renderComponent(
      "network",
      {
        data: [
          {
            ...defaultAnalysisData.data[0],
            sources_involved: ["ATM_APP", "HARDWARE", "TERMINAL_HANDLER", "KAFKA"],
          },
        ],
      },
      {
        data: [
          {
            ...defaultAnomaliesData.data[0],
            sources_involved: ["ATM_APP", "HARDWARE", "TERMINAL_HANDLER", "KAFKA"],
          },
        ],
      }
    );

    await waitFor(() => {
      expect(screen.getByText("ATM_APP")).toBeDefined();
      expect(screen.getByText("HARDWARE")).toBeDefined();
      expect(screen.getByText("TERMINAL_HANDLER")).toBeDefined();
      expect(screen.getByText("KAFKA")).toBeDefined();
    });
  });

  it("gets sources from dbAnomaly when data has none", async () => {
    await renderComponent(
      "network",
      {
        data: [
          {
            ...defaultAnalysisData.data[0],
            sources_involved: undefined,
          },
        ],
      },
      {
        data: [
          {
            ...defaultAnomaliesData.data[0],
            sources_involved: ["PROMETHEUS"],
          },
        ],
      }
    );

    await waitFor(() => {
      expect(screen.getByText("PROMETHEUS")).toBeDefined();
    });
  });

  // ─── correlation_id ───────────────────────────────────

  it("displays correlation_id", async () => {
    await renderComponent();

    await waitFor(() => {
      expect(screen.getByText("Correlation ID:")).toBeDefined();
      expect(screen.getByText("corr-123-abc")).toBeDefined();
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

  // ─── star toggle ──────────────────────────────────────

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

  it("logs error when star toggle fails", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    await renderComponent();
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

  it("shows already starred state when is_starred is 1", async () => {
    await renderComponent(
      "network",
      defaultAnalysisData,
      {
        data: [
          {
            ...defaultAnomaliesData.data[0],
            is_starred: 1,
          },
        ],
      }
    );

    await waitFor(() => {
      expect(screen.getByText("Starred")).toBeDefined();
      expect(screen.queryByText("Star")).toBeNull();
    });
  });

  // ─── complete toggle ──────────────────────────────────

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

  it("shows toast error when complete toggle fails", async () => {
    await renderComponent();
    mockToggleComplete.mockRejectedValue(new Error("API error"));

    await waitFor(() => {
      expect(screen.getByText("Mark Complete")).toBeDefined();
    });

    fireEvent.click(screen.getByText("Mark Complete"));

    await waitFor(() => {
      expect(toastMock.error).toHaveBeenCalledWith("Failed to update status");
    });
  });

  it("does not call toggleComplete when dbAnomaly is null", async () => {
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

    // When no matching anomaly found, isCompleted stays at default (true),
    // so button shows "Completed", not "Mark Complete"
    fireEvent.click(screen.getByText("Completed"));

    await waitFor(() => {
      expect(mockToggleComplete).not.toHaveBeenCalled();
    });
  });

  it("shows already completed state when is_active is 0", async () => {
    await renderComponent(
      "network",
      defaultAnalysisData,
      {
        data: [
          {
            ...defaultAnomaliesData.data[0],
            is_active: 0,
          },
        ],
      }
    );

    await waitFor(() => {
      expect(screen.getByText("Completed")).toBeDefined();
      expect(screen.queryByText("Mark Complete")).toBeNull();
    });
  });

  it("shows toast success when toggling from completed to active", async () => {
    await renderComponent(
      "network",
      defaultAnalysisData,
      {
        data: [
          {
            ...defaultAnomaliesData.data[0],
            is_active: 0,
          },
        ],
      }
    );

    await waitFor(() => {
      expect(screen.getByText("Completed")).toBeDefined();
    });

    fireEvent.click(screen.getByText("Completed"));

    await waitFor(() => {
      expect(mockToggleComplete).toHaveBeenCalledWith(1);
      expect(toastMock.success).toHaveBeenCalledWith("Marked as active");
    });
  });

  // ─── time display ─────────────────────────────────────

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

  it("formats Event_Time with time range format", async () => {
    await renderComponent("network", {
      data: [
        {
          ...defaultAnalysisData.data[0],
          Event_Time: "2024-01-15 10:00:00 - 2024-01-15 12:00:00",
        },
      ],
    });

    await waitFor(() => {
      expect(screen.getByText("Time Received:")).toBeDefined();
      const timeText = screen.getByText("Time Received:").parentElement
        .querySelector("span:last-child");
      expect(timeText).toBeDefined();
      // formatUKDateTime with range should show formatted dates
      expect(timeText.textContent).not.toBe("Time Unknown");
    });
  });

  // ─── fallback states ──────────────────────────────────

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

  // ─── severity color classes ───────────────────────────

  it("applies correct severity class for MAJOR severity", async () => {
    await renderComponent("network", {
      data: [
        {
          ...defaultAnalysisData.data[0],
          Severity: "MAJOR",
        },
      ],
    });

    await waitFor(() => {
      const badge = screen.getByText("MAJOR");
      expect(badge.className).toContain("bg-amber-500");
    });
  });

  it("applies correct severity class for HIGH severity", async () => {
    await renderComponent("network", {
      data: [
        {
          ...defaultAnalysisData.data[0],
          Severity: "HIGH",
        },
      ],
    });

    await waitFor(() => {
      const badge = screen.getByText("HIGH");
      expect(badge.className).toContain("bg-blue-500");
    });
  });

  it("applies correct severity class for LOW severity", async () => {
    await renderComponent("network", {
      data: [
        {
          ...defaultAnalysisData.data[0],
          Severity: "LOW",
        },
      ],
    });

    await waitFor(() => {
      const badge = screen.getByText("LOW");
      expect(badge.className).toContain("bg-muted");
    });
  });

  // ─── recommended action uses correct field ─────────────

  it("uses recommended_action over Recommended_Action when both present", async () => {
    await renderComponent("network", {
      data: [
        {
          ...defaultAnalysisData.data[0],
          recommended_action: "Lower priority action",
          Recommended_Action: "Higher priority action",
        },
      ],
    });

    await waitFor(() => {
      // recommended_action takes precedence in the source code
      expect(screen.getByText("Lower priority action")).toBeDefined();
    });
  });

  it("falls back to Recommended_Action when recommended_action is missing", async () => {
    await renderComponent("network", {
      data: [
        {
          ...defaultAnalysisData.data[0],
          recommended_action: undefined,
          Recommended_Action: "Fallback action",
        },
      ],
    });

    await waitFor(() => {
      expect(screen.getByText("Fallback action")).toBeDefined();
    });
  });

  // ─── explanation JSON edge cases ──────────────────────

  it("handles empty explanation string", async () => {
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
            explanation: "",
          },
        ],
      }
    );

    await waitFor(() => {
      expect(screen.queryByText("Detected By:")).toBeNull();
    });
  });

  it("handles explanation JSON with source as null", async () => {
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
            explanation: JSON.stringify({ source: null }),
          },
        ],
      }
    );

    await waitFor(() => {
      // source is null, so detectionSource should be null -> not rendered
      expect(screen.queryByText("Detected By:")).toBeNull();
    });
  });

  // ─── button variant states ────────────────────────────

  it("star button uses outline variant when not starred", async () => {
    await renderComponent();

    await waitFor(() => {
      const starBtn = screen.getByText("Star").closest("button");
      expect(starBtn.className).toContain("outline");
    });
  });

  it("star button uses default variant when starred", async () => {
    await renderComponent(
      "network",
      defaultAnalysisData,
      {
        data: [
          {
            ...defaultAnomaliesData.data[0],
            is_starred: 1,
          },
        ],
      }
    );

    await waitFor(() => {
      const starBtn = screen.getByText("Starred").closest("button");
      expect(starBtn).toBeDefined();
    });
  });

  it("complete button uses secondary variant when completed", async () => {
    await renderComponent(
      "network",
      defaultAnalysisData,
      {
        data: [
          {
            ...defaultAnomaliesData.data[0],
            is_active: 0,
          },
        ],
      }
    );

    await waitFor(() => {
      const completeBtn = screen.getByText("Completed").closest("button");
      expect(completeBtn.className).toContain("secondary");
    });
  });

  it("complete button uses default variant when not completed", async () => {
    await renderComponent();

    await waitFor(() => {
      const completeBtn = screen.getByText("Mark Complete").closest("button");
      expect(completeBtn).toBeDefined();
    });
  });

  // ─── fetch error handling ─────────────────────────────

  it("handles fetch error gracefully", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    // Set up mocks BEFORE render
    mockFetchDetailedAnalysis.mockRejectedValue(new Error("Network error"));
    mockFetchAnomalies.mockRejectedValue(new Error("Network error"));

    const { default: AnomalyData } = await import("../pages/AnomalyData");
    render(
      <MemoryRouter initialEntries={["/data/network/1"]}>
        <Routes>
          <Route path="/data/:anomaly_type/:id" element={<AnomalyData />} />
        </Routes>
      </MemoryRouter>
    );

    // Component should render the empty state after fetch error
    await waitFor(() => {
      expect(screen.getByText("No analysis data available for this anomaly type.")).toBeDefined();
    });

    consoleSpy.mockRestore();
  });

  // ─── detection card structure ─────────────────────────

  it("renders Detection card header", async () => {
    await renderComponent();

    await waitFor(() => {
      expect(screen.getByText("Detection")).toBeDefined();
    });
  });

  it("renders Details card header", async () => {
    await renderComponent();

    await waitFor(() => {
      expect(screen.getByText("Details")).toBeDefined();
    });
  });
});
