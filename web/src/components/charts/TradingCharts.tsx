import { useEffect, useRef } from "react";
import { createChart, type IChartApi, type UTCTimestamp } from "lightweight-charts";

export type OhlcBar = {
  t: number;
  o: number;
  h: number;
  l: number;
  c: number;
  v: number;
};

const CHART_OPTS = {
  layout: {
    background: { color: "transparent" },
    textColor: "#8b949e",
  },
  grid: {
    vertLines: { color: "#21262d" },
    horzLines: { color: "#21262d" },
  },
  rightPriceScale: { borderColor: "#30363d" },
  timeScale: { borderColor: "#30363d", timeVisible: true, secondsVisible: false },
  crosshair: { mode: 1 as const },
};

/** jsdom has no real canvas — skip createChart so Vitest stays quiet. */
function canvasUsable(): boolean {
  if (import.meta.env.MODE === "test") return false;
  try {
    return !!document.createElement("canvas").getContext("2d");
  } catch {
    return false;
  }
}

/**
 * TradingView Lightweight Charts candlestick + volume.
 */
export function CandleStickChart({ candles }: { candles: OhlcBar[] }) {
  const hostRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = hostRef.current;
    if (!el || candles.length === 0 || !canvasUsable()) return;

    let chart: IChartApi | undefined;
    try {
      chart = createChart(el, {
        ...CHART_OPTS,
        width: el.clientWidth || 640,
        height: 360,
      });
    } catch {
      // headless without canvas — keep empty host for layout/tests.
      return;
    }

    const candleSeries = chart.addCandlestickSeries({
      upColor: "#3fb950",
      downColor: "#f85149",
      borderVisible: false,
      wickUpColor: "#3fb950",
      wickDownColor: "#f85149",
    });

    const byTime = new Map<number, OhlcBar>();
    for (const c of candles) {
      byTime.set(Math.floor(c.t / 1000), c);
    }
    const sorted = [...byTime.entries()].sort((a, b) => a[0] - b[0]);

    candleSeries.setData(
      sorted.map(([time, c]) => ({
        time: time as UTCTimestamp,
        open: c.o,
        high: c.h,
        low: c.l,
        close: c.c,
      })),
    );

    const volSeries = chart.addHistogramSeries({
      color: "#6e7681",
      priceFormat: { type: "volume" },
      priceScaleId: "vol",
    });
    chart.priceScale("vol").applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });
    volSeries.setData(
      sorted.map(([time, c]) => ({
        time: time as UTCTimestamp,
        value: c.v,
        color: c.c >= c.o ? "rgba(63,185,80,0.5)" : "rgba(248,81,73,0.5)",
      })),
    );

    chart.timeScale().fitContent();

    const ro = new ResizeObserver(() => {
      if (el.clientWidth > 0) chart?.applyOptions({ width: el.clientWidth });
    });
    ro.observe(el);

    return () => {
      ro.disconnect();
      chart?.remove();
    };
  }, [candles]);

  return (
    <div
      ref={hostRef}
      data-testid="candles-chart"
      role="img"
      aria-label="Candlestick chart"
      style={{ width: "100%", height: 360 }}
    />
  );
}

export type VolumeBar = {
  strike: number;
  ce_volume: number;
  pe_volume: number;
  total_volume: number;
};

/**
 * CE (+) / PE (−) mirrored histogram by strike via Lightweight Charts.
 */
export function VolumeProfileLwChart({ profile }: { profile: VolumeBar[] }) {
  const hostRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = hostRef.current;
    if (!el || profile.length === 0 || !canvasUsable()) return;

    let chart: IChartApi | undefined;
    try {
      chart = createChart(el, {
        ...CHART_OPTS,
        width: el.clientWidth || 640,
        height: 320,
        timeScale: { borderColor: "#30363d", visible: false },
      });
    } catch {
      return;
    }

    const ceSeries = chart.addHistogramSeries({
      color: "#3fb950",
      priceFormat: { type: "volume" },
      title: "CE",
    });
    const peSeries = chart.addHistogramSeries({
      color: "#f85149",
      priceFormat: { type: "volume" },
      title: "PE",
    });

    // Sequential timestamps so LW Charts can plot strike rows as a series.
    const base = 1_700_000_000;
    ceSeries.setData(
      profile.map((p, i) => ({
        time: (base + i * 86_400) as UTCTimestamp,
        value: p.ce_volume,
      })),
    );
    peSeries.setData(
      profile.map((p, i) => ({
        time: (base + i * 86_400) as UTCTimestamp,
        value: -p.pe_volume,
      })),
    );

    chart.timeScale().fitContent();

    const ro = new ResizeObserver(() => {
      if (el.clientWidth > 0) chart?.applyOptions({ width: el.clientWidth });
    });
    ro.observe(el);

    return () => {
      ro.disconnect();
      chart?.remove();
    };
  }, [profile]);

  return (
    <div
      ref={hostRef}
      data-testid="volume-profile-chart"
      role="img"
      aria-label="CE/PE volume profile by strike"
      style={{ width: "100%", height: 320 }}
    />
  );
}
