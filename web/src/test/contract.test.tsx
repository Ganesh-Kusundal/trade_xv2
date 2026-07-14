/**
 * SPA↔backend contract tests.
 *
 * Drives components with `createFakeApi` payloads shaped exactly like the
 * live responses asserted in `tests/integration/api/test_contract.py`
 * (CALL/PUT chain, lake quote without bid/ask, Candle[], cancellable statuses).
 */
import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { Candles } from "../components/Candles";
import { MarketQuotes } from "../components/MarketQuotes";
import { Options } from "../components/Options";
import { Orders, CANCELLABLE_ORDER_STATUSES } from "../components/Orders";
import { createFakeApi } from "./fakeApi";
import { renderWithClient } from "./render";
import type {
  OptionChainResponse,
  OrderResponse,
  QuoteResponse,
} from "../types";

/** Mirrors backend `OrderStatus` non-terminal values that may be cancelled. */
const BACKEND_CANCELLABLE = ["OPEN", "PARTIALLY_FILLED"] as const;

describe("SPA↔backend contract", () => {
  it("normalizes CALL/PUT option_type to CE/PE in the chain table", async () => {
    const chain: OptionChainResponse = {
      underlying: "NIFTY",
      expiry: "2026-03-26",
      count: 2,
      contracts: [
        {
          symbol: "NIFTY_MONTH_1_-10_CALL",
          expiry: "2026-03-26",
          strike: 21700,
          option_type: "CALL",
          ltp: 1074.15,
          volume: 0,
          oi: 7280,
        },
        {
          symbol: "NIFTY_MONTH_1_-10_PUT",
          expiry: "2026-03-26",
          strike: 21700,
          option_type: "PUT",
          ltp: 80.25,
          volume: 100,
          oi: 4200,
        },
      ],
    };
    const api = createFakeApi({
      optionChain: vi.fn().mockResolvedValue(chain),
    });
    renderWithClient(<Options />, api);

    const table = await screen.findByTestId("options-chain");
    const cells = Array.from(table.querySelectorAll("tbody tr td:nth-child(2)")).map(
      (el) => el.textContent,
    );
    expect(cells).toEqual(["CE", "PE"]);
  });

  it("also maps CE/PE literals to CE/PE (backend may emit either)", async () => {
    const chain: OptionChainResponse = {
      underlying: "NIFTY",
      expiry: "all",
      count: 2,
      contracts: [
        {
          symbol: "X",
          expiry: "",
          strike: 25000,
          option_type: "CE",
          ltp: 1,
          volume: 1,
          oi: 1,
        },
        {
          symbol: "Y",
          expiry: "",
          strike: 25000,
          option_type: "PE",
          ltp: 1,
          volume: 1,
          oi: 1,
        },
      ],
    };
    renderWithClient(
      <Options />,
      createFakeApi({ optionChain: vi.fn().mockResolvedValue(chain) }),
    );
    const table = await screen.findByTestId("options-chain");
    const cells = Array.from(table.querySelectorAll("tbody tr td:nth-child(2)")).map(
      (el) => el.textContent,
    );
    expect(cells).toEqual(["CE", "PE"]);
  });

  it("renders — for missing bid/ask on lake-backed quotes", async () => {
    const quote: QuoteResponse = {
      symbol: "RELIANCE",
      exchange: "NSE",
      ltp: 1269.0,
      timestamp: 0,
      // bid/ask intentionally omitted (live-only)
      volume: 18684,
      oi: 0,
    };
    renderWithClient(
      <MarketQuotes />,
      createFakeApi({ quote: vi.fn().mockResolvedValue(quote) }),
    );
    expect(await screen.findByTestId("quote-ltp")).toHaveTextContent("1,269.00");
    expect(screen.getByTestId("quote-bid")).toHaveTextContent("—");
    expect(screen.getByTestId("quote-ask")).toHaveTextContent("—");
  });

  it("coerces string live-quote numbers via Number()", async () => {
    const quote = {
      symbol: "RELIANCE",
      exchange: "NSE",
      ltp: "1269.5" as unknown as number,
      timestamp: 0,
      bid: "1268.0" as unknown as number,
      ask: "1270.0" as unknown as number,
      volume: "100" as unknown as number,
      oi: 0,
    } satisfies QuoteResponse;
    renderWithClient(
      <MarketQuotes />,
      createFakeApi({ quote: vi.fn().mockResolvedValue(quote) }),
    );
    expect(await screen.findByTestId("quote-ltp")).toHaveTextContent("1,269.50");
    expect(screen.getByTestId("quote-bid")).toHaveTextContent("1,268.00");
    expect(screen.getByTestId("quote-ask")).toHaveTextContent("1,270.00");
  });

  it("renders a candle chart for a real Candle[] shape", async () => {
    const candles = {
      symbol: "RELIANCE",
      timeframe: "1m",
      exchange: "NSE",
      count: 3,
      candles: [
        { t: 1, o: 100, h: 110, l: 90, c: 105, v: 1000, oi: 0 },
        { t: 2, o: 105, h: 112, l: 104, c: 110, v: 1100, oi: 0 },
        { t: 3, o: 110, h: 115, l: 108, c: 112, v: 1200, oi: 0 },
      ],
    };
    renderWithClient(
      <Candles />,
      createFakeApi({ candles: vi.fn().mockResolvedValue(candles) }),
    );
    expect(await screen.findByTestId("candles-chart")).toBeInTheDocument();
  });

  it("cancel whitelist matches backend OrderStatus non-terminal set", () => {
    expect([...CANCELLABLE_ORDER_STATUSES]).toEqual([...BACKEND_CANCELLABLE]);
  });

  it("enables Cancel only for documented cancellable statuses", async () => {
    const orders: OrderResponse[] = [
      {
        order_id: "o1",
        symbol: "RELIANCE",
        exchange: "NSE",
        transaction_type: "BUY",
        order_type: "LIMIT",
        quantity: 1,
        price: 100,
        status: "OPEN",
        filled_quantity: 0,
        average_price: null,
        timestamp: new Date().toISOString(),
      },
      {
        order_id: "o2",
        symbol: "RELIANCE",
        exchange: "NSE",
        transaction_type: "BUY",
        order_type: "LIMIT",
        quantity: 1,
        price: 100,
        status: "FILLED",
        filled_quantity: 1,
        average_price: 100,
        timestamp: new Date().toISOString(),
      },
    ];
    renderWithClient(
      <Orders />,
      createFakeApi({
        orders: vi.fn().mockResolvedValue({ orders, count: 2 }),
      }),
    );
    const buttons = await screen.findAllByRole("button", { name: "Cancel" });
    expect(buttons).toHaveLength(2);
    expect(buttons[0]).not.toBeDisabled();
    expect(buttons[1]).toBeDisabled();
  });
});
