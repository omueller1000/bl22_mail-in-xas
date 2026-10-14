import type { DataView, SweepInfo } from "../api/client";

/** Derived spectra (requirements §11.3). */
export const SPECTRUM_LABELS: Record<string, string> = {
  sample_trans: "Sample transmission · ln(i0/i1)",
  ref_trans: "Reference transmission · ln(i1/i2)",
  fy_norm: "Fluorescence · fy/i0",
  sdd_roi1: "SDD ROI 1 · Σ roi1/i0",
  sdd_roi2: "SDD ROI 2 · Σ roi2/i0",
};

export const VIEW_LABELS: Record<DataView, string> = {
  spectrum: "Spectra",
  raw: "Raw signals",
  mu: "μ(E)",
  chi: "χ(k)",
};

/** The spectrum that matches the detection mode, if the data has it (§11.1). */
export function defaultSpectrum(sweep: SweepInfo): string | undefined {
  const preferred = {
    transmission: "sample_trans",
    transmission_tfy: "fy_norm",
    transmission_sdd: "sdd_roi1",
  }[sweep.measured.detection];
  return sweep.spectra.includes(preferred) ? preferred : sweep.spectra[0];
}

export function axisLabels(view: DataView, name: string | undefined): [string, string] {
  switch (view) {
    case "mu":
      return ["Energy (eV)", "μ(E)"];
    case "chi":
      return ["k (Å⁻¹)", "k²χ(k) (Å⁻²)"];
    case "spectrum":
      return ["Energy (eV)", (name && SPECTRUM_LABELS[name]?.split(" · ")[1]) ?? name ?? ""];
    default:
      return ["Energy (eV)", name ?? ""];
  }
}
