import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import ReactDOM from "react-dom/client";
import { App } from "./App";
import "./styles/lifeos/style.css";
import "./styles/lifeos/theme-v2.css";
import "./styles/lifeos/project-studio.css";
import "./styles/lifeos/focus.css";
import "./styles/lifeos/public.css";
import "./styles/global.css";
import "./styles/separated.css";

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
