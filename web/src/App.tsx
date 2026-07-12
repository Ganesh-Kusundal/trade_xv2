import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { BrokerStatus } from "./components/BrokerStatus";
import { MarketQuotes } from "./components/MarketQuotes";
import { Positions } from "./components/Positions";
import { Orders } from "./components/Orders";
import { Diagnostics } from "./components/Diagnostics";
import { Performance } from "./components/Performance";

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Navigate to="/broker" replace />} />
        <Route path="/broker" element={<BrokerStatus />} />
        <Route path="/market" element={<MarketQuotes />} />
        <Route path="/positions" element={<Positions />} />
        <Route path="/orders" element={<Orders />} />
        <Route path="/diagnostics" element={<Diagnostics />} />
        <Route path="/performance" element={<Performance />} />
        <Route path="*" element={<Navigate to="/broker" replace />} />
      </Route>
    </Routes>
  );
}
