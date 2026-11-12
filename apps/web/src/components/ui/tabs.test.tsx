// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Composer } from "@/features/analyst/composer";

import { Tabs } from "./tabs";

afterEach(cleanup);

function Harness() {
  const [value, setValue] = useState<"a" | "b" | "c">("a");
  return (
    <Tabs
      label="Views"
      value={value}
      onChange={setValue}
      items={[
        { key: "a", label: "Alpha" },
        { key: "b", label: "Beta" },
        { key: "c", label: "Gamma" },
      ]}
      renderPanel={(k) => <p>panel {k}</p>}
    />
  );
}

describe("Tabs keyboard support", () => {
  it("arrow keys, Home and End move selection and focus", () => {
    render(<Harness />);
    const alpha = screen.getByRole("tab", { name: "Alpha" });
    expect(alpha.getAttribute("aria-selected")).toBe("true");
    fireEvent.keyDown(alpha, { key: "ArrowRight" });
    expect(screen.getByRole("tab", { name: "Beta" }).getAttribute("aria-selected")).toBe("true");
    expect(document.activeElement).toBe(screen.getByRole("tab", { name: "Beta" }));
    fireEvent.keyDown(document.activeElement!, { key: "End" });
    expect(screen.getByText("panel c")).toBeTruthy();
    fireEvent.keyDown(document.activeElement!, { key: "ArrowRight" }); // wraps
    expect(screen.getByRole("tab", { name: "Alpha" }).getAttribute("aria-selected")).toBe("true");
  });

  it("only the selected tab is in the tab order", () => {
    render(<Harness />);
    const tabIndexes = screen.getAllByRole("tab").map((t) => t.getAttribute("tabindex"));
    expect(tabIndexes).toEqual(["0", "-1", "-1"]);
  });
});

describe("Composer", () => {
  it("submits on Enter, keeps Shift+Enter for new lines, and ignores blank input", () => {
    const onSubmit = vi.fn();
    render(<Composer onSubmit={onSubmit} placeholder="Ask" />);
    const box = screen.getByLabelText("Ask a question about your data");
    fireEvent.keyDown(box, { key: "Enter" });
    expect(onSubmit).not.toHaveBeenCalled();
    fireEvent.change(box, { target: { value: "Top products?" } });
    fireEvent.keyDown(box, { key: "Enter", shiftKey: true });
    expect(onSubmit).not.toHaveBeenCalled();
    fireEvent.keyDown(box, { key: "Enter" });
    expect(onSubmit).toHaveBeenCalledWith("Top products?");
  });

  it("does not submit while disabled", () => {
    const onSubmit = vi.fn();
    render(<Composer onSubmit={onSubmit} placeholder="Ask" disabled />);
    const box = screen.getByLabelText("Ask a question about your data");
    fireEvent.change(box, { target: { value: "Q" } });
    fireEvent.keyDown(box, { key: "Enter" });
    expect(onSubmit).not.toHaveBeenCalled();
    expect((screen.getByRole("button", { name: "Ask" }) as HTMLButtonElement).disabled).toBe(true);
  });
});
