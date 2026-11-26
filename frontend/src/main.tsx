import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "react-router-dom";
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "./styles/tokens.css";
import "./styles/app.css";
import { router } from "./app/App";
import { ThemeCtx, applyTheme, initialTheme, type Theme } from "./app/theme";

const client = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: true,
      refetchIntervalInBackground: false, // hidden tabs stop polling
    },
  },
});

function Root() {
  const [theme, set] = useState<Theme>(() => {
    const t = initialTheme();
    applyTheme(t);
    return t;
  });
  const setTheme = (t: Theme) => {
    applyTheme(t);
    set(t);
  };
  return (
    <ThemeCtx.Provider value={{ theme, setTheme }}>
      <QueryClientProvider client={client}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </ThemeCtx.Provider>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Root />
  </StrictMode>,
);
