import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { type ReactNode, useState } from "react";

import { theme } from "./theme";

/** Everything the app needs around its pages: UI library, notifications, server-data cache. */
export function Providers({
  children,
  env = "default",
}: {
  children: ReactNode;
  /** "test" disables transitions and portals (https://mantine.dev/guides/vitest/). */
  env?: "default" | "test";
}) {
  const [queryClient] = useState(() => new QueryClient());

  return (
    <MantineProvider theme={theme} defaultColorScheme="auto" env={env}>
      <Notifications />
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </MantineProvider>
  );
}
