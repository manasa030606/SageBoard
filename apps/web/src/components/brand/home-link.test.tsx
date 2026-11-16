// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { auth } from "@/lib/api/endpoints";
import { ApiError } from "@/lib/api/errors";
import type { SessionInfo } from "@/lib/api/types";

import { HomeLink } from "./home-link";

vi.mock("@/lib/api/endpoints", () => ({ auth: { peek: vi.fn() } }));

const peek = vi.mocked(auth.peek);
const LANDING = "/";
const DASHBOARD = "/app/dashboard";

const session = (overrides: Partial<SessionInfo> = {}): SessionInfo => ({
  user: { id: "u1", email: "a@example.test", full_name: "A" } as SessionInfo["user"],
  csrf_token: "t",
  auth_mode: "session",
  ...overrides,
});
const href = () => screen.getByRole("link").getAttribute("href");

beforeEach(() => {
  peek.mockReset();
});
afterEach(cleanup);

describe("HomeLink", () => {
  it("while the session is still being checked it does not assume the user is signed in", async () => {
    let answer: (info: SessionInfo) => void = () => {};
    peek.mockReturnValue(new Promise<SessionInfo>((resolve) => (answer = resolve)));
    render(<HomeLink>logo</HomeLink>);
    await waitFor(() => expect(peek).toHaveBeenCalled());
    expect(href()).toBe(LANDING);
    expect(screen.getByRole("link").getAttribute("aria-label")).toBe("Sageboard home");
    expect(screen.getByRole("link").getAttribute("data-auth-state")).toBe("loading");

    answer(session()); // and once the API says yes, it becomes the dashboard link
    await screen.findByRole("link", { name: "Sageboard dashboard" });
  });

  it("sends a signed-in user to the dashboard", async () => {
    peek.mockResolvedValue(session());
    render(<HomeLink>logo</HomeLink>);
    const link = await screen.findByRole("link", { name: "Sageboard dashboard" });
    expect(link.getAttribute("href")).toBe(DASHBOARD);
    expect(link.getAttribute("data-auth-state")).toBe("signed-in");
  });

  it("treats a 401 as a visitor", async () => {
    peek.mockRejectedValue(new ApiError({ status: 401, code: "UNAUTHENTICATED", message: "no" }));
    render(<HomeLink>logo</HomeLink>);
    await waitFor(() => expect(peek).toHaveBeenCalled());
    await Promise.resolve();
    expect(href()).toBe(LANDING);
    expect(screen.getByRole("link").getAttribute("data-auth-state")).toBe("visitor");
  });

  it.each([
    ["a server error", new ApiError({ status: 500, code: "INTERNAL", message: "boom" })],
    ["an unreachable API", new ApiError({ status: 0, code: "NETWORK_ERROR", message: "down" })],
    ["a non-API failure", new Error("unexpected")],
  ])("treats %s as a visitor", async (_name, error) => {
    peek.mockRejectedValue(error);
    render(<HomeLink>logo</HomeLink>);
    await waitFor(() => expect(peek).toHaveBeenCalled());
    await Promise.resolve();
    expect(href()).toBe(LANDING);
  });

  it("does not count the API's demo mode (no sign-in exists) as signed in", async () => {
    peek.mockResolvedValue(session({ auth_mode: "demo" }));
    render(<HomeLink>logo</HomeLink>);
    await waitFor(() => expect(peek).toHaveBeenCalled());
    await Promise.resolve();
    expect(href()).toBe(LANDING);
  });

  it("does not count a reply without a user as signed in", async () => {
    peek.mockResolvedValue({ csrf_token: "t", auth_mode: "session" } as unknown as SessionInfo);
    render(<HomeLink>logo</HomeLink>);
    await waitFor(() => expect(peek).toHaveBeenCalled());
    await Promise.resolve();
    expect(href()).toBe(LANDING);
  });

  it("asks again on every page load: an earlier answer is not reused", async () => {
    peek.mockResolvedValueOnce(session());
    const first = render(<HomeLink>logo</HomeLink>);
    await screen.findByRole("link", { name: "Sageboard dashboard" });
    first.unmount();

    peek.mockRejectedValueOnce(
      new ApiError({ status: 401, code: "UNAUTHENTICATED", message: "no" }),
    );
    render(<HomeLink>logo</HomeLink>);
    await waitFor(() => expect(peek).toHaveBeenCalledTimes(2));
    await Promise.resolve();
    expect(href()).toBe(LANDING);
  });

  it("asks once for several logos on one page", async () => {
    peek.mockResolvedValue(session());
    render(
      <>
        <HomeLink>a</HomeLink>
        <HomeLink>b</HomeLink>
      </>,
    );
    await waitFor(() =>
      expect(screen.getAllByRole("link").every((l) => l.getAttribute("href") === DASHBOARD)).toBe(
        true,
      ),
    );
    expect(peek).toHaveBeenCalledTimes(1);
  });
});
