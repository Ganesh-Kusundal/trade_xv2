import type { ReactElement } from "react";
import { render, type RenderOptions } from "@testing-library/react";
import { ApiProvider } from "../api/ApiContext";
import type { TradingApi } from "../api/client";
import { createFakeApi } from "./fakeApi";

/** Render a component wrapped with a (fake) ApiClient. */
export function renderWithClient(
  ui: ReactElement,
  client: TradingApi = createFakeApi(),
  options?: Omit<RenderOptions, "wrapper">,
) {
  return render(ui, {
    wrapper: ({ children }) => <ApiProvider client={client}>{children}</ApiProvider>,
    ...options,
  });
}
