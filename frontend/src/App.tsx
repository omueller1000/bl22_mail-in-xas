import { createBrowserRouter } from "react-router";
import { RouterProvider } from "react-router/dom";

import { RequireRole, RequireUser } from "./auth/guards";
import { Layout } from "./layout/Layout";
import { AccountPage } from "./pages/AccountPage";
import { HomePage } from "./pages/HomePage";
import { LoginPage } from "./pages/LoginPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { RegisterPage } from "./pages/RegisterPage";
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
            {
              element: <RequireRole role="operator" />,
              children: [{ path: "users", element: <UsersPage /> }],
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
