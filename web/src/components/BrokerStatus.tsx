import { useApi } from "../api/ApiContext";
import { useAsync } from "../hooks/useAsync";

/**
 * Broker connectivity / status widget (mirrors the TUI `BrokerConsoleWidget`
 * account summary and the `BrokerStatus` panel).
 *
 * NOTE: "connect" is server-side — the broker (e.g. the paper broker) is
 * wired at backend startup via config, not via a client call. This component
 * therefore reads the live `/live/health` + `/live/capabilities` endpoints to
 * surface the active broker and its readiness.
 */
export function BrokerStatus() {
  const api = useApi();
  const health = useAsync(() => api.brokerHealth(), []);
  const caps = useAsync(() => api.brokerCapabilities(), []);

  return (
    <section className="panel" aria-label="Broker status">
      <h2>Broker Status</h2>

      {health.loading && <p className="muted">Connecting to broker…</p>}
      {health.error && (
        <p className="error" role="alert">
          Broker not connected: {health.error.message}
        </p>
      )}

      {health.data && (
        <dl className="kv">
          <div>
            <dt>Broker</dt>
            <dd data-testid="broker-name">{health.data.broker}</dd>
          </div>
          <div>
            <dt>Status</dt>
            <dd
              className={
                health.data.status === "healthy"
                  ? "ok"
                  : health.data.status === "degraded"
                    ? "warn"
                    : "error"
              }
              data-testid="broker-status"
            >
              {health.data.status}
            </dd>
          </div>
          <div>
            <dt>Last check</dt>
            <dd>{new Date(health.data.timestamp).toLocaleString()}</dd>
          </div>
        </dl>
      )}

      {caps.data && (
        <details>
          <summary>Capabilities</summary>
          <pre data-testid="broker-capabilities">
            {JSON.stringify(caps.data.capabilities, null, 2)}
          </pre>
        </details>
      )}
    </section>
  );
}
