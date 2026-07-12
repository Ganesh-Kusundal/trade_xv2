import { createContext, useContext, type ReactNode } from "react";
import { ApiClient, type TradingApi } from "./client";

const defaultClient = new ApiClient();

const ApiContext = createContext<TradingApi>(defaultClient);

export function ApiProvider({
  client,
  children,
}: {
  client?: TradingApi;
  children: ReactNode;
}) {
  return <ApiContext.Provider value={client ?? defaultClient}>{children}</ApiContext.Provider>;
}

export function useApi(): TradingApi {
  return useContext(ApiContext);
}
