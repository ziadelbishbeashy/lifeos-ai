import { useQuery } from "@tanstack/react-query";
import { apiGet, apiPost, resetCsrfToken } from "../api/client";
import type { SessionState } from "../api/types";

export const sessionQueryKey = ["session"] as const;

export function useSession() {
  return useQuery({
    queryKey: sessionQueryKey,
    queryFn: () => apiGet<SessionState>("/api/v1/session"),
    staleTime: 30_000,
    retry: false,
  });
}

export async function login(input: {
  email: string;
  password: string;
  remember: boolean;
}) {
  resetCsrfToken();
  return apiPost<SessionState>("/api/v1/auth/login", input);
}

export async function register(input: {
  name: string;
  email: string;
  password: string;
  confirm_password: string;
}) {
  resetCsrfToken();
  return apiPost<SessionState>("/api/v1/auth/register", input);
}

export async function logout() {
  const result = await apiPost<SessionState>("/api/v1/auth/logout");
  resetCsrfToken();
  return result;
}
