import { describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MarketQuotes } from "../components/MarketQuotes";
import { createFakeApi } from "./fakeApi";
import { renderWithClient } from "./render";
import type { QuoteResponse } from "../types";

describe("MarketQuotes", () => {
  it("renders a quote after querying a symbol", async () => {
    const quote: QuoteResponse = {
      symbol: "RELIANCE",
      exchange: "NSE",
      ltp: 2450.5,
      timestamp: 1710000000000,
      bid: 2450.0,
      ask: 2451.0,
      volume: 12345,
      oi: 0,
    };
    const api = createFakeApi({ quote: vi.fn().mockResolvedValue(quote) });
    renderWithClient(<MarketQuotes />, api);

    const input = screen.getByLabelText("Symbol");
    await userEvent.clear(input);
    await userEvent.type(input, "RELIANCE");
    await userEvent.click(screen.getByRole("button", { name: "Query" }));

    expect(await screen.findByTestId("quote-ltp")).toHaveTextContent("2,450.50");
    expect(api.quote).toHaveBeenCalledWith("RELIANCE");
  });

  it("shows an error when the quote request fails", async () => {
    const api = createFakeApi({
      quote: vi.fn().mockRejectedValue(new Error("404: No quote data found for XYZ")),
    });
    renderWithClient(<MarketQuotes />, api);

    const input = screen.getByLabelText("Symbol");
    await userEvent.clear(input);
    await userEvent.type(input, "XYZ");
    await userEvent.click(screen.getByRole("button", { name: "Query" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("No quote data");
  });

  it("renders the live feed status indicator", async () => {
    renderWithClient(<MarketQuotes />, createFakeApi());
    await waitFor(() => {
      expect(screen.getByTestId("ws-status").textContent).toMatch(/Live feed:/);
    });
  });
});
