import { useEffect } from "react";
import { navigate } from "../core/navigation";

/** Legacy compatibility only. I19 now lives inside Ask LifeOS. */
export function AgentPage() {
  useEffect(() => { navigate("/ask", true); }, []);
  return null;
}
