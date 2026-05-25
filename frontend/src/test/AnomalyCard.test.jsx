import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import AnomalyCard from "../components/AnomalyCard";

const defaultProps = {
  id: 1,
  title: "Network Timeout Cascade",
  atm_id: "ATM-GB-0001",
  severity: "CRITICAL",
  anomaly_type: "A1",
  update_time: "2026-03-05 09:15",
  is_starred: false,
  is_active: 1,
  toggle_star: vi.fn(),
  onCompleted: vi.fn(),
};

function renderCard(props = {}) {
  return render(
    <MemoryRouter>
      <AnomalyCard {...defaultProps} {...props} />
    </MemoryRouter>
  );
}

describe("AnomalyCard", () => {
  it("renders title and ATM ID", () => {
    renderCard();
    expect(screen.getByText("Network Timeout Cascade")).toBeDefined();
    expect(screen.getByText("ATM-GB-0001")).toBeDefined();
  });

  it("renders severity badge", () => {
    renderCard();
    expect(screen.getByText("CRITICAL")).toBeDefined();
  });

  it("renders entity type as ATM", () => {
    renderCard();
    expect(screen.getByText("ATM")).toBeDefined();
  });

  it("renders entity type as Server for ATM-SERVER- IDs", () => {
    renderCard({ atm_id: "ATM-SERVER-001" });
    expect(screen.getByText("Server")).toBeDefined();
  });

  it("shows filled star when starred", () => {
    renderCard({ is_starred: true });
    expect(screen.getByLabelText("Unstar anomaly")).toBeDefined();
  });

  it("shows empty star when not starred", () => {
    renderCard({ is_starred: false });
    expect(screen.getByLabelText("Star anomaly")).toBeDefined();
  });

  it("calls toggle_star on star click", () => {
    const toggleStar = vi.fn();
    renderCard({ toggle_star: toggleStar });
    fireEvent.click(screen.getByLabelText("Star anomaly"));
    expect(toggleStar).toHaveBeenCalledWith(1);
  });

  it("calls onCompleted on complete click", () => {
    const onCompleted = vi.fn();
    renderCard({ onCompleted });
    fireEvent.click(screen.getByLabelText("Mark as completed"));
    expect(onCompleted).toHaveBeenCalledWith(1);
  });

  it("shows active icon when inactive", () => {
    renderCard({ is_active: 0 });
    expect(screen.getByLabelText("Mark as active")).toBeDefined();
  });

  it("navigates to detail page on View click", () => {
    renderCard();
    fireEvent.click(screen.getByText("View"));
  });

  it("renders all severity variants", () => {
    renderCard({ severity: "MAJOR" });
    expect(screen.getByText("MAJOR")).toBeDefined();
  });
});
