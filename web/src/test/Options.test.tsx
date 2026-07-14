import { describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Options } from "../components/Options";
import { createFakeApi } from "./fakeApi";
import { renderWithClient } from "./render";
import type {
  MaxPainResponse,
  OptionChainResponse,
  PCRResponse,
  VolumeProfileResponse,
} from "../types";

describe("Options", () => {
  const chain: OptionChainResponse = {
    underlying: "NIFTY",
    expiry: "2026-07-30",
    count: 2,
    contracts: [
      { symbol: "NIFTY_WEEK_1_-10_CALL", expiry: "2026-07-30", strike: 25000, option_type: "CALL", ltp: 120.5, volume: 1000, oi: 5000 },
      { symbol: "NIFTY_WEEK_1_-10_PUT", expiry: "2026-07-30", strike: 25000, option_type: "PUT", ltp: 80.25, volume: 800, oi: 4200 },
    ],
  };
  const pcr: PCRResponse = {
    timestamp: 0, underlying: "NIFTY", expiry_kind: "MONTH", expiry_date: "2026-07-30", spot: 24980,
    pcr_volume: 0.9, pcr_oi: 1.1, total_ce_volume: 100, total_pe_volume: 90, total_ce_oi: 5000, total_pe_oi: 5500,
  };
  const maxPain: MaxPainResponse = {
    timestamp: 0, underlying: "NIFTY", expiry_kind: "MONTH", expiry_date: "2026-07-30", spot: 24980,
    max_pain_strike: 24800, total_pain_at_max_pain: 0, distance_from_spot: 180, position_vs_spot: "below_spot",
  };
  const vol: VolumeProfileResponse = {
    underlying: "NIFTY", expiry: "2026-07-30", strikes: [24800, 25000],
    profile: [
      { strike: 24800, ce_volume: 200, pe_volume: 100, total_volume: 300 },
      { strike: 25000, ce_volume: 1000, pe_volume: 800, total_volume: 1800 },
    ],
    count: 2,
  };

  it("renders summary tiles and volume chart from real endpoint data", async () => {
    const api = createFakeApi({
      optionChain: vi.fn().mockResolvedValue(chain),
      pcr: vi.fn().mockResolvedValue(pcr),
      maxPain: vi.fn().mockResolvedValue(maxPain),
      ivSurface: vi.fn().mockResolvedValue({
        timestamp: 0, underlying: "NIFTY", expiry_kind: "MONTH", expiry_date: "2026-07-30", spot: 24980,
        atm_strike: 24980, atm_iv: 0.14, otm_put_iv: 0.16, otm_call_iv: 0.13, iv_skew: 0.03,
        put_call_iv_ratio: null, days_to_expiry: 17,
      }),
      volumeProfile: vi.fn().mockResolvedValue(vol),
    });
    renderWithClient(<Options />, api);

    expect(await screen.findByTestId("tile-spot")).toHaveTextContent("24,980.00");
    expect(await screen.findByTestId("tile-max-pain")).toHaveTextContent("24,800.00");
    expect(screen.getByTestId("tile-pcr-oi")).toHaveTextContent("1.100");
    expect(screen.getByTestId("tile-atm-iv")).toHaveTextContent("+14.00%");
    expect(screen.getByTestId("volume-profile-chart")).toBeInTheDocument();
    expect(screen.getByTestId("options-chain").querySelectorAll("tbody tr").length).toBe(2);
    // Lake emits CALL/PUT; SPA normalizes to CE/PE.
    const types = Array.from(
      screen.getByTestId("options-chain").querySelectorAll("tbody tr td:nth-child(2)"),
    ).map((el) => el.textContent);
    expect(types).toEqual(["CE", "PE"]);
  });

  it("shows an error alert when the chain request fails", async () => {
    const api = createFakeApi({
      optionChain: vi.fn().mockRejectedValue(new Error("404: No option data found for XYZ")),
    });
    renderWithClient(<Options />, api);

    expect(await screen.findByRole("alert")).toHaveTextContent("No option data");
  });

  it("re-queries when the underlying is changed and submitted", async () => {
    const api = createFakeApi({ optionChain: vi.fn().mockResolvedValue(chain) });
    renderWithClient(<Options />, api);

    const input = screen.getByTestId("options-underlying");
    await userEvent.clear(input);
    await userEvent.type(input, "BANKNIFTY");
    await userEvent.click(screen.getByRole("button", { name: "Analyze" }));

    await waitFor(() => expect(api.optionChain).toHaveBeenLastCalledWith("BANKNIFTY", { strike_range: 10 }));
  });
});
