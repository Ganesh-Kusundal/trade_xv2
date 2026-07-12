import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { Positions } from "../components/Positions";
import { createFakeApi } from "./fakeApi";
import { renderWithClient } from "./render";
import type { PositionsResponse } from "../types";

describe("Positions", () => {
  it("renders a table of positions", async () => {
    const data: PositionsResponse = {
      positions: [
        {
          symbol: "RELIANCE",
          exchange: "NSE",
          quantity: 10,
          average_price: 2400,
          current_price: 2450,
          unrealized_pnl: 500,
          realized_pnl: 0,
          pnl_pct: 2.08,
        },
      ],
      count: 1,
      total_pnl: 500,
      total_pnl_percent: 2.08,
    };
    const api = createFakeApi({ positions: vi.fn().mockResolvedValue(data) });
    renderWithClient(<Positions />, api);

    expect(await screen.findByText("RELIANCE")).toBeInTheDocument();
    expect(api.positions).toHaveBeenCalledTimes(1);
  });

  it("shows an empty state when there are no positions", async () => {
    const api = createFakeApi({
      positions: vi.fn().mockResolvedValue({
        positions: [],
        count: 0,
        total_pnl: 0,
        total_pnl_percent: 0,
      }),
    });
    renderWithClient(<Positions />, api);

    expect(await screen.findByTestId("positions-empty")).toHaveTextContent(
      "No open positions",
    );
  });

  it("shows an error when the request fails", async () => {
    const api = createFakeApi({
      positions: vi.fn().mockRejectedValue(new Error("503: OMS not initialized")),
    });
    renderWithClient(<Positions />, api);

    expect(await screen.findByRole("alert")).toHaveTextContent("OMS not initialized");
  });
});
