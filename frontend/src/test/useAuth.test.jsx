import { describe, it, expect } from "vitest";
import { useAuth, AuthContext } from "../auth/useAuth";
import { render, screen } from "@testing-library/react";

describe("useAuth", () => {
  it("throws error when used outside AuthProvider", () => {
    expect(() => useAuth()).toThrow();
  });

  it("returns context when used within AuthProvider", () => {
    function TestComp() {
      const ctx = useAuth();
      return <div data-testid="ctx">{typeof ctx.login}</div>;
    }

    render(
      <AuthContext.Provider value={{ token: "test", user: null, loading: false, login: () => {}, logout: () => {} }}>
        <TestComp />
      </AuthContext.Provider>
    );

    expect(screen.getByTestId("ctx").textContent).toBe("function");
  });
});
