import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { render } from "@testing-library/react";
import { useState } from "react";
import { ErrorBoundary } from "../components/ErrorBoundary";

function ThrowingComponent({ shouldThrow }: { shouldThrow: boolean }) {
  if (shouldThrow) throw new Error("Test crash");
  return <div>All good</div>;
}

describe("ErrorBoundary", () => {
  it("renders children when there is no error", () => {
    render(
      <ErrorBoundary>
        <div>Child content</div>
      </ErrorBoundary>,
    );
    expect(screen.getByText("Child content")).toBeInTheDocument();
  });

  it("renders fallback when a child throws", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <ErrorBoundary>
        <ThrowingComponent shouldThrow />
      </ErrorBoundary>,
    );
    spy.mockRestore();

    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("Something went wrong")).toBeInTheDocument();
    expect(screen.getByText("Test crash")).toBeInTheDocument();
    expect(screen.getByText("Try again")).toBeInTheDocument();
  });

  it("clears error state when reset is triggered and child no longer throws", async () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    const user = userEvent.setup();

    function ControlledThrow() {
      const [throwing, setThrowing] = useState(true);
      return (
        <>
          <ErrorBoundary>
            <ThrowingComponent shouldThrow={throwing} />
          </ErrorBoundary>
          <button type="button" onClick={() => setThrowing(false)}>
            Stop throwing
          </button>
        </>
      );
    }

    render(<ControlledThrow />);
    expect(screen.getByText("Something went wrong")).toBeInTheDocument();

    await user.click(screen.getByText("Stop throwing"));
    await user.click(screen.getByText("Try again"));

    expect(screen.getByText("All good")).toBeInTheDocument();
    spy.mockRestore();
  });
});
