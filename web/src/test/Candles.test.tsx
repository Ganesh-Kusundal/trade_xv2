import { describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Candles } from "../components/Candles";
import { createFakeApi } from "./fakeApi";
import { renderWithClient } from "./render";
import type { CandlesResponse } from "../types";

describe("Candles", () => {
  const candles: CandlesResponse = {
    symbol: "NIFTY",
    timeframe: "1d",
    candles: [
      { t: 1719801600000, o: 24000, h: 24100, l: 23950, c: 24050, v: 100, oi: 0 },
      { t: 1719888000000, o: 24050, h: 24200, l: 24000, c: 24180, v: 120, oi: 0 },
    ],
    count: 2,
  };

  it("renders a candlestick chart after loading", async () => {
    const api = createFakeApi({ candles: vi.fn().mockResolvedValue(candles) });
    renderWithClient(<Candles />, api);

    expect(await screen.findByTestId("candles-chart")).toBeInTheDocument();
    expect(screen.getByTestId("candles-count")).toHaveTextContent("2 candles");
  });

  it("shows an error alert when the candle fetch fails", async () => {
    const api = createFakeApi({
      candles: vi.fn().mockRejectedValue(new Error("404: No candle data found for XYZ/1d")),
    });
    renderWithClient(<Candles />, api);

    expect(await screen.findByRole("alert")).toHaveTextContent("No candle data");
  });

  it("re-queries when symbol and timeframe are submitted", async () => {
    const api = createFakeApi({ candles: vi.fn().mockResolvedValue(candles) });
    renderWithClient(<Candles />, api);

    const input = screen.getByTestId("candles-symbol");
    await userEvent.clear(input);
    await userEvent.type(input, "BANKNIFTY");
    await userEvent.selectOptions(screen.getByLabelText("Timeframe"), "5m");
    await userEvent.click(screen.getByRole("button", { name: "Load" }));

    await waitFor(() =>
      expect(api.candles).toHaveBeenLastCalledWith({
        symbol: "BANKNIFTY",
        timeframe: "5m",
        limit: 200,
      }),
    );
  });
});
