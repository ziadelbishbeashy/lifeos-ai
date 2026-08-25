import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import ReactDOM from "react-dom/client";
import { App } from "./App";

/* Keep the original LifeOS design system authoritative.  The old Phase-2
   global.css contained a second application shell/grid system and must not be
   loaded in the fully separated frontend. */
import "./styles/react-base.css";
import "./styles/separated.css";
import "./styles/lifeos/public.css";
import "./styles/lifeos/style.css";
import "./styles/lifeos/theme-v2.css";
import "./styles/lifeos/project-studio.css";
import "./styles/lifeos/focus.css";
import "./styles/react-native-extras.css";
import "./styles/visual-parity.css";
import "./styles/layout-foundation.css";
import "./styles/lifeos/polish.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      refetchOnWindowFocus: false,
    },
  },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <QueryClientProvider client={queryClient}>
    <App />
  </QueryClientProvider>,
);
