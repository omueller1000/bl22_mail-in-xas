import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";

import { Providers } from "../Providers";

/** Render a component with the app's providers and an in-memory router. */
export function renderWithProviders(ui: ReactElement, { route = "/" }: { route?: string } = {}) {
  return render(
    <Providers>
      <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
    </Providers>,
  );
}

/** Shows the current location, to assert on redirects. */
export function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname + location.search}</div>;
}

/** Routes for page tests: the page under test plus probes at redirect targets. */
export function withProbes(path: string, element: ReactElement) {
  return (
    <Routes>
      <Route path={path} element={element} />
      <Route path="*" element={<LocationProbe />} />
    </Routes>
  );
}
