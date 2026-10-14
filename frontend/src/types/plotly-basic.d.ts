// The parts of Plotly's "basic" bundle (scatter, bar, pie) that the data viewer uses.
declare module "plotly.js-basic-dist-min" {
  const Plotly: {
    react(
      element: HTMLElement,
      data: object[],
      layout?: object,
      config?: object,
    ): Promise<unknown>;
    purge(element: HTMLElement): void;
    Plots: { resize(element: HTMLElement): void };
  };
  export default Plotly;
}
