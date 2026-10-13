import { createBrowserRouter } from "react-router";
import { RouterProvider } from "react-router/dom";

import { RequireRole, RequireUser } from "./auth/guards";
import { Layout } from "./layout/Layout";
import { AccountPage } from "./pages/AccountPage";
import { FrameConfigPage } from "./pages/FrameConfigPage";
import { FramesPage } from "./pages/FramesPage";
import { HomePage } from "./pages/HomePage";
import { LoginPage } from "./pages/LoginPage";
import { MaterialsPage } from "./pages/MaterialsPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { BarcodesPage } from "./pages/operator/BarcodesPage";
import { RequestDetailPage } from "./pages/operator/RequestDetailPage";
import { RequestsPage } from "./pages/operator/RequestsPage";
import { ShippingPage } from "./pages/operator/ShippingPage";
import { RegisterPage } from "./pages/RegisterPage";
import { SamplesPage } from "./pages/SamplesPage";
import { UsersPage } from "./pages/UsersPage";
import { Providers } from "./Providers";

// BASE_URL is "/mail-in-xas/" (or "/mail-in-xas/dev/"); the router wants it without the slash.
const basename = import.meta.env.BASE_URL.replace(/\/$/, "");

const router = createBrowserRouter(
  [
    {
      element: <Layout />,
      children: [
        { index: true, element: <HomePage /> },
        { path: "login", element: <LoginPage /> },
        { path: "register", element: <RegisterPage /> },
        {
          element: <RequireUser />,
          children: [
            { path: "account", element: <AccountPage /> },
            { path: "materials", element: <MaterialsPage /> },
            { path: "samples", element: <SamplesPage /> },
            { path: "frames", element: <FramesPage /> },
            { path: "frames/:barcode", element: <FrameConfigPage /> },
            {
              element: <RequireRole role="operator" />,
              children: [
                { path: "users", element: <UsersPage /> },
                { path: "operator/requests", element: <RequestsPage /> },
                { path: "operator/requests/:requestId", element: <RequestDetailPage /> },
                { path: "operator/barcodes", element: <BarcodesPage /> },
                { path: "operator/shipping", element: <ShippingPage /> },
              ],
            },
          ],
        },
        { path: "*", element: <NotFoundPage /> },
      ],
    },
  ],
  { basename },
);

export function App() {
  return (
    <Providers>
      <RouterProvider router={router} />
    </Providers>
  );
}
