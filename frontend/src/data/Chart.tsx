import { Box, useComputedColorScheme } from "@mantine/core";
import { useEffect, useRef } from "react";

export interface Trace {
  name: string;
  x: (number | null)[];
  y: (number | null)[];
  /** Drawn thicker and on top, e.g. the merged curve. */
  emphasis?: boolean;
  dashed?: boolean;
  color?: string;
}

interface ChartProps {
  traces: Trace[];
  xLabel: string;
  yLabel: string;
  height?: number;
}

/** A line chart with zoom and pan. Plotly (about 1 MB) is loaded only when a chart is shown. */
export function Chart({ traces, xLabel, yLabel, height = 460 }: ChartProps) {
  const element = useRef<HTMLDivElement>(null);
  const dark = useComputedColorScheme("light") === "dark";

  useEffect(() => {
    let cancelled = false;
    const el = element.current;
    import("plotly.js-basic-dist-min").then(({ default: Plotly }) => {
      if (cancelled || !el) return;
      const text = dark ? "#c9c9c9" : "#495057";
      const grid = dark ? "#373a40" : "#e9ecef";
      const axis = (title: string) => ({
        title: { text: title },
        gridcolor: grid,
        zerolinecolor: grid,
        automargin: true,
      });
      void Plotly.react(
        el,
        traces.map((t) => ({
          type: "scatter",
          mode: "lines",
          name: t.name,
          x: t.x,
          y: t.y,
          line: {
            width: t.emphasis ? 3 : 1.2,
            ...(t.emphasis && { color: dark ? "#ffffff" : "#000000" }),
            ...(t.dashed && { dash: "dash" }),
            ...(t.color && { color: t.color }),
          },
        })),
        {
          height,
          margin: { l: 60, r: 20, t: 10, b: 50 },
          paper_bgcolor: "rgba(0,0,0,0)",
          plot_bgcolor: "rgba(0,0,0,0)",
          font: { color: text },
          xaxis: axis(xLabel),
          yaxis: axis(yLabel),
          legend: { orientation: "h", y: -0.2 },
          uirevision: `${xLabel}|${yLabel}`, // keep the zoom while sweeps are toggled
        },
        { responsive: true, displaylogo: false, modeBarButtonsToRemove: ["select2d", "lasso2d"] },
      );
    });
    return () => {
      cancelled = true;
    };
  }, [traces, xLabel, yLabel, height, dark]);

  useEffect(() => {
    const el = element.current;
    return () => {
      if (el) void import("plotly.js-basic-dist-min").then(({ default: P }) => P.purge(el));
    };
  }, []);

  return <Box ref={element} mih={height} />;
}
