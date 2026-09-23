import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import LoginPage from "@/pages/LoginPage";

vi.mock("@/components/SessionProvider", () => ({
  useSession: () => ({
    t: (key: string) => key,
  }),
}));

const originalConfig = window.__TELEGRAM_AUTO_POSTER__;

const setBotUsername = (botUsername?: string) => {
  window.__TELEGRAM_AUTO_POSTER__ = botUsername ? { botUsername } : {};
};

afterEach(() => {
  window.__TELEGRAM_AUTO_POSTER__ = originalConfig;
});

describe("LoginPage", () => {
  it("injects the Telegram login widget script when the bot username is configured", () => {
    setBotUsername("meme_autoposter_bot");

    const { container } = render(<LoginPage />);

    const script = container.querySelector<HTMLScriptElement>(
      'script[src="https://telegram.org/js/telegram-widget.js?22"]',
    );
    expect(script).toBeInTheDocument();
    expect(script).toHaveAttribute("data-telegram-login", "meme_autoposter_bot");
    expect(script).toHaveAttribute("data-size", "large");
    expect(script).toHaveAttribute("data-auth-url", `${window.location.origin}/auth`);
    expect(script).toHaveAttribute("data-request-access", "write");
  });

  it("clears injected widget DOM when unmounted", () => {
    setBotUsername("meme_autoposter_bot");

    const { container, unmount } = render(<LoginPage />);
    const widgetContainer = container.querySelector("script")?.parentElement;
    expect(widgetContainer).toBeTruthy();
    widgetContainer?.appendChild(document.createElement("iframe"));

    unmount();

    expect(widgetContainer).toBeEmptyDOMElement();
  });

  it("shows a configuration message instead of the widget when the bot username is missing", () => {
    setBotUsername();

    const { container } = render(<LoginPage />);

    expect(
      screen.getByText("Telegram bot username is not configured."),
    ).toBeInTheDocument();
    expect(container.querySelector("script")).not.toBeInTheDocument();
  });
});
