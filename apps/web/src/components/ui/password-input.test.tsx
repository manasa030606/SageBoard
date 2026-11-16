// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { PasswordInput } from "./field";

afterEach(cleanup);

function setup() {
  render(
    <>
      <label htmlFor="pw">Password</label>
      <PasswordInput id="pw" defaultValue="hunter2hunter2" />
    </>,
  );
  return screen.getByLabelText("Password", { selector: "input" }) as HTMLInputElement;
}

describe("PasswordInput", () => {
  it("is hidden by default", () => {
    const input = setup();
    expect(input.type).toBe("password");
    expect(
      screen.getByRole("button", { name: "Show characters" }).getAttribute("aria-pressed"),
    ).toBe("false");
  });

  it("shows the text when the button is pressed and hides it again on a second press", () => {
    const input = setup();
    fireEvent.click(screen.getByRole("button", { name: "Show characters" }));
    expect(input.type).toBe("text");
    expect(input.value).toBe("hunter2hunter2");
    fireEvent.click(screen.getByRole("button", { name: "Hide characters" }));
    expect(input.type).toBe("password");
  });

  it("never submits the form, and a mouse press does not take focus from the input", () => {
    let submitted = false;
    render(
      <form
        onSubmit={(e) => {
          e.preventDefault();
          submitted = true;
        }}
      >
        <PasswordInput aria-label="Secret" />
      </form>,
    );
    const button = screen.getByRole("button");
    expect(button.getAttribute("type")).toBe("button");
    fireEvent.click(button);
    expect(submitted).toBe(false);
    // the button cancels mousedown, which is what stops the browser moving focus to it
    expect(fireEvent.mouseDown(button)).toBe(false);
  });

  it("does not add a second element that a search for the field by its label would match", () => {
    setup();
    expect(screen.getAllByLabelText(/password/i)).toHaveLength(1);
  });
});
