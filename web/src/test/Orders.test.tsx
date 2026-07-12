import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Orders } from "../components/Orders";
import { createFakeApi } from "./fakeApi";
import { renderWithClient } from "./render";

describe("Orders form validation", () => {
  it("has submit enabled with valid default form", async () => {
    const api = createFakeApi({ orders: vi.fn().mockResolvedValue({ orders: [], count: 0 }) });
    renderWithClient(<Orders />, api);

    const btn = await screen.findByTestId("place-order");
    expect(btn).not.toBeDisabled();
  });

  it("disables submit when symbol is empty", async () => {
    const user = userEvent.setup();
    const api = createFakeApi({ orders: vi.fn().mockResolvedValue({ orders: [], count: 0 }) });
    renderWithClient(<Orders />, api);

    const symbolInput = await screen.findByLabelText("Order symbol");
    await user.clear(symbolInput);

    const btn = screen.getByTestId("place-order");
    expect(btn).toBeDisabled();
  });

  it("disables submit when quantity is zero", async () => {
    const user = userEvent.setup();
    const api = createFakeApi({ orders: vi.fn().mockResolvedValue({ orders: [], count: 0 }) });
    renderWithClient(<Orders />, api);

    const qtyInput = screen.getByLabelText("Quantity");
    await user.clear(qtyInput);
    await user.type(qtyInput, "0");

    const btn = screen.getByTestId("place-order");
    expect(btn).toBeDisabled();
  });

  it("disables submit when LIMIT order has no price", async () => {
    const user = userEvent.setup();
    const api = createFakeApi({ orders: vi.fn().mockResolvedValue({ orders: [], count: 0 }) });
    renderWithClient(<Orders />, api);

    const priceInput = screen.getByLabelText("Price");
    await user.clear(priceInput);

    const btn = screen.getByTestId("place-order");
    expect(btn).toBeDisabled();
  });

  it("enables submit for MARKET order without price", async () => {
    const user = userEvent.setup();
    const api = createFakeApi({ orders: vi.fn().mockResolvedValue({ orders: [], count: 0 }) });
    renderWithClient(<Orders />, api);

    const orderTypeSelect = screen.getByLabelText("Order type");
    await user.selectOptions(orderTypeSelect, "MARKET");

    const priceInput = screen.getByLabelText("Price");
    await user.clear(priceInput);

    const btn = screen.getByTestId("place-order");
    expect(btn).not.toBeDisabled();
  });
});
