import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The app is served below a sub-path, matching the public URL:
//   prod: https://www-ssrl.slac.stanford.edu/mail-in-xas/   (default mode)
//   dev:  /mail-in-xas/dev/                                  (`--mode dev`)
// The API lives at `<base>api`, e.g. /mail-in-xas/api.
export default defineConfig(({ mode }) => {
  const base = mode === "dev" ? "/mail-in-xas/dev/" : "/mail-in-xas/";
  // Local backend; override with BACKEND_URL if it runs elsewhere.
  const backend = process.env.BACKEND_URL ?? "http://127.0.0.1:8010";

  return {
    base,
    plugins: [react()],
    server: {
      // Not Vite's default 5173, which other local projects commonly use.
      port: 5180,
      strictPort: true,
      // Forward API calls unchanged, so frontend and API share one origin (as behind nginx).
      proxy: { [`${base}api`]: { target: backend } },
    },
    test: {
      environment: "jsdom",
      setupFiles: ["./src/test/setup.ts"],
    },
  };
});
