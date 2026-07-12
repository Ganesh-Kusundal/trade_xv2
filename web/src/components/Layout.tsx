import { NavLink, Outlet } from "react-router-dom";

const NAV = [
  { to: "/broker", label: "Broker" },
  { to: "/market", label: "Market" },
  { to: "/positions", label: "Positions" },
  { to: "/orders", label: "Orders" },
  { to: "/diagnostics", label: "Diagnostics" },
  { to: "/performance", label: "Performance" },
];

export function Layout() {
  return (
    <div className="app">
      <header className="topbar">
        <strong className="brand">TradeXV2 · Web Terminal</strong>
        <nav className="nav">
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
            >
              {n.label}
            </NavLink>
          ))}
        </nav>
      </header>
      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}
