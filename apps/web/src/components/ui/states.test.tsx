// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { EmptyState, ErrorState, Notice } from "./states";

afterEach(cleanup);

describe("EmptyState", () => {
  it("shows the title, description and action", () => {
    render(
      <EmptyState
        title="No reports yet"
        description="Save an answer to start."
        action={<button>Ask</button>}
      />,
    );
    expect(screen.getByRole("heading", { name: "No reports yet" })).toBeTruthy();
    expect(screen.getByText("Save an answer to start.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Ask" })).toBeTruthy();
  });

  it("omits optional parts it was not given", () => {
    const { container } = render(<EmptyState title="Nothing" />);
    expect(container.querySelector("p")).toBeNull();
  });
});

describe("ErrorState", () => {
  it("is announced as an alert, with a default title and the error code", () => {
    render(<ErrorState description="The API is unreachable." code="NETWORK" />);
    const alert = screen.getByRole("alert");
    expect(alert.textContent).toContain("Something went wrong");
    expect(alert.textContent).toContain("The API is unreachable.");
    expect(screen.getByText("NETWORK")).toBeTruthy();
  });

  it("renders a retry action", () => {
    render(<ErrorState title="Couldn't load" description="x" action={<button>Retry</button>} />);
    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
  });
});

describe("Notice", () => {
  it("uses role=alert only for errors", () => {
    render(
      <>
        <Notice tone="error" title="Failed">
          bad
        </Notice>
        <Notice tone="success" title="Saved">
          ok
        </Notice>
      </>,
    );
    expect(screen.getAllByRole("alert")).toHaveLength(1);
    expect(screen.getAllByRole("status")).toHaveLength(1);
  });
});
