import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router";

import { Providers } from "../Providers";

/** Render a component with the app's providers and an in-memory router. */
export function renderWithProviders(ui: ReactElement) {
  return render(
    <Providers>
      <MemoryRouter>{ui}</MemoryRouter>
    </Providers>,
  );
}
