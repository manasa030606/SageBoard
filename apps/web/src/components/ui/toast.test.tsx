// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider, useToast } from "./toast";

beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

function Trigger({ n = 1 }: { n?: number }) {
  const { notify } = useToast();
  return (
    <button
      onClick={() => {
        for (let i = 1; i <= n; i++) notify({ tone: "success", title: `Toast ${i}` });
      }}
    >
      go
    </button>
  );
}

const wrap = (n?: number) =>
  render(
    <ToastProvider>
      <Trigger n={n} />
    </ToastProvider>,
  );

describe("Toasts", () => {
  it("shows a notification and removes it after a few seconds", () => {
    wrap();
    fireEvent.click(screen.getByText("go"));
    expect(screen.getByText("Toast 1")).toBeTruthy();
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(screen.queryByText("Toast 1")).toBeNull();
  });

  it("can be dismissed by hand", () => {
    wrap();
    fireEvent.click(screen.getByText("go"));
    fireEvent.click(screen.getByLabelText("Dismiss notification"));
    expect(screen.queryByText("Toast 1")).toBeNull();
  });

  it("keeps at most three on screen, dropping the oldest", () => {
    wrap(5);
    fireEvent.click(screen.getByText("go"));
    expect(screen.queryByText("Toast 1")).toBeNull();
    expect(screen.queryByText("Toast 2")).toBeNull();
    expect(screen.getByText("Toast 3")).toBeTruthy();
    expect(screen.getByText("Toast 5")).toBeTruthy();
  });

  it("refuses to be used outside the provider", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => undefined);
    expect(() => render(<Trigger />)).toThrow(/ToastProvider/);
    spy.mockRestore();
  });
});
