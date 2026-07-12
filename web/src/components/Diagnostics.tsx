import { useApi } from "../api/ApiContext";
import { useAsync } from "../hooks/useAsync";

interface Check {
  name: string;
  status: "PASS" | "WARN" | "FAIL" | "…";
  detail: string;
}

/**
 * Diagnostics widget (mirrors the TUI `DiagnosticsConsoleWidget` "doctor"
 * suite). The TUI runs local connectivity checks; the web surface reuses the
 * backend health endpoints as the diagnostic source of truth:
 *   - GET /health            (liveness)
 *   - GET /health/readyz    (readiness + service checks)
 *   - GET /live/health      (active broker connectivity)
 */
export function Diagnostics() {
  const api = useApi();
  const health = useAsync(() => api.health().then(() => true).catch(() => false), []);
  const ready = useAsync<{ ready: boolean; checks: Record<string, unknown> } | null>(
    () => api.readiness().catch(() => null),
    [],
  );
  const broker = useAsync(() => api.brokerHealth().catch(() => null), []);

  const checks: Check[] = [
    {
      name: "API liveness (/health)",
      status: health.loading ? "…" : health.data ? "PASS" : "FAIL",
      detail: health.error ? health.error.message : health.data ? "API reachable" : "No response",
    },
    {
      name: "Readiness (/health/readyz)",
      status: ready.loading
        ? "…"
        : ready.data?.ready
          ? "PASS"
          : ready.data
            ? "FAIL"
            : "WARN",
      detail: ready.data
        ? JSON.stringify(ready.data.checks)
        : ready.error
          ? ready.error.message
          : "Readiness not reported",
    },
    {
      name: "Broker connectivity (/live/health)",
      status: broker.loading
        ? "…"
        : broker.data
          ? "PASS"
          : "WARN",
      detail: broker.data
        ? `${broker.data.broker} · ${broker.data.status}`
        : broker.error
          ? broker.error.message
          : "No live broker wired",
    },
  ];

  return (
    <section className="panel" aria-label="Diagnostics">
      <h2>Diagnostics</h2>
      <table data-testid="diagnostics-table">
        <thead>
          <tr>
            <th>Check</th>
            <th>Status</th>
            <th>Observation</th>
          </tr>
        </thead>
        <tbody>
          {checks.map((c) => (
            <tr key={c.name}>
              <td>{c.name}</td>
              <td className={c.status === "PASS" ? "ok" : c.status === "FAIL" ? "error" : "warn"}>
                {c.status}
              </td>
              <td className="muted">{c.detail}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
