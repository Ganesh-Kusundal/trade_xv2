# Dependency & Flow Diagrams

Mermaid diagrams for the target architecture. See `target-layering.md` for the
contract these visualize.

## 1. Target Layer Dependency

```mermaid
graph TD
  UI[interface: web / api / tui / agent] --> RT[runtime: composition root]
  UI --> APP[application: use-cases]
  RT --> INF[infrastructure: adapters]
  RT --> PLG[(plugins: brokers + exchanges)]
  INF --> APP
  APP --> DOM[domain: entities / ports / events]
  INF -.implements ports.-> DOM
  PLG -.discovered by.-> RT
  DOM -.nothing inward.-> DOM
```

Rule: `domain` depends on nothing inward. `runtime` is the only layer that touches
concrete plugins.

## 2. Bounded Contexts

```mermaid
graph LR
  MD[Market Data] --> APP
  INST[Instruments] --> APP
  EX[Execution / OMS] --> APP
  PF[Portfolio] --> APP
  RK[Risk] --> EX
  SA[Strategy / Analytics] --> APP
  AUTH[Identity / Auth] --> INF
  INF[Platform / Infra] --> APP
  OBS[Observability] --> INF
  EXC[Exchange plugin] --> MD
  APP[application] --> DOM[domain]
```

## 3. Order Lifecycle (current → target)

Current (fragile reflection coupling at kill-switch):

```mermaid
sequenceDiagram
  participant S as Strategy/Scanner
  participant O as TradingOrchestrator
  participant E as ExecutionPlanner
  participant P as OrderPlacer
  participant OM as OrderManager
  participant RK as RiskManager
  participant B as Broker (via submit_fn)

  S->>O: candidate
  O->>E: plan()
  E->>P: place()
  P->>OM: place_order()
  OM->>RK: pre-trade check
  RK-->>OM: approved / rejected
  OM->>B: submit_fn(order)
  B-->>OM: OrderResponse
  Note over O,RK: kill-switch read via getattr(oM.risk_manager) -- fragile (baseline G7)
```

Target (injected `RiskGate`, no reflection):

```mermaid
sequenceDiagram
  participant S as Strategy/Scanner
  participant O as TradingOrchestrator
  participant G as RiskGate (port, injected)
  participant OM as OrderManager
  participant B as BrokerAdapter (plugin)
  S->>O: candidate
  O->>G: is_open() / approve(order)
  G-->>O: Decision
  O->>OM: place_order()
  OM->>B: submit(order)
  B-->>OM: OrderResponse
  OM->>OM: on_order_update heals state
  OM->>REC: ReconciliationEngine.drift()
  REC-->>OM: DriftItem -> auto-heal -> POSITION_DRIFT event
```

## 4. Reconciliation on Hot Path (target, baseline G6)

```mermaid
stateDiagram-v2
  [*] --> LocalState
  LocalState --> BrokerFeed: on_order_update / on_trade
  BrokerFeed --> Reconcile: periodic + on update
  Reconcile --> InSync: no drift
  Reconcile --> DriftDetected: drift found
  DriftDetected --> Heal: apply broker-authoritative
  Heal --> InSync: state corrected
  DriftDetected --> Alert: heal fails
  Alert --> [*]
  InSync --> [*]
```

Today `Reconcile` is a separate service, not on the `BrokerFeed` path — drift is
detected but local state updates only via event handlers, so a dropped feed silently
diverges. P5-6 wires `Reconcile` directly into `BrokerFeed`.

## 5. Plugin Discovery (target, baseline G1/G2)

```mermaid
flowchart TD
  START[Runtime startup] --> REG{Load entry-points}
  REG --> B1[broker: dhan]
  REG --> B2[broker: upstox]
  REG --> B3[broker: paper]
  REG --> X1[exchange: nse]
  B1 --> SEL[Select active by broker_id enum]
  B2 --> SEL
  B3 --> SEL
  X1 --> SEL
  SEL --> INJ[Inject BrokerAdapter + ExchangeAdapter into application]
  INJ --> READY[System ready]
```

No string branching (`_active_name == "dhan"`); selection is by typed `broker_id`.
