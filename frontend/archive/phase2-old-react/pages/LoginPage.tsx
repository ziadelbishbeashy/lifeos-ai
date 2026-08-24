import { FormEvent, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { login, sessionQueryKey } from "../auth/session";

export function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: login,
    onSuccess: async (session) => {
      queryClient.setQueryData(sessionQueryKey, session);
      const state = location.state as { from?: string } | null;
      navigate(state?.from || "/dashboard", { replace: true });
    },
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    mutation.mutate({ email, password, remember });
  }

  const errorMessage = mutation.error instanceof ApiError
    ? mutation.error.message
    : mutation.isError
      ? "LifeOS could not sign you in. Please try again."
      : null;

  return (
    <div className="auth-page">
      <section className="auth-story">
        <Link className="auth-brand" to="/login">
          <span className="brand-mark">L</span>
          <span><strong>LifeOS AI</strong><small>Execution Intelligence</small></span>
        </Link>

        <div className="auth-story-copy">
          <span className="eyebrow">Your workspace, connected</span>
          <h1>Turn scattered work into <em>clear execution.</em></h1>
          <p>
            Projects, tasks, notes and Document Brain stay connected so the
            next useful action is always easier to find.
          </p>
        </div>

        <div className="auth-proof-grid">
          <div><strong>Projects</strong><span>Goals, phases and progress</span></div>
          <div><strong>Document Brain</strong><span>Grounded AI with evidence</span></div>
          <div><strong>Focus</strong><span>Priorities from real work</span></div>
        </div>
      </section>

      <main className="auth-panel">
        <div className="auth-card">
          <span className="eyebrow">Welcome back</span>
          <h2>Log in to LifeOS</h2>
          <p className="auth-card-lead">Continue from your current execution workspace.</p>

          {errorMessage && <div className="form-alert error">{errorMessage}</div>}

          <form onSubmit={submit} className="auth-form">
            <label>
              <span>Email</span>
              <input
                type="email"
                autoComplete="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="you@example.com"
                required
              />
            </label>

            <label>
              <span>Password</span>
              <input
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="Your password"
                required
              />
            </label>

            <label className="check-row">
              <input
                type="checkbox"
                checked={remember}
                onChange={(event) => setRemember(event.target.checked)}
              />
              <span>Keep me signed in</span>
            </label>

            <button className="primary-button auth-submit" type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? "Signing in…" : "Log in"}
            </button>
          </form>

          <p className="auth-switch">
            New to LifeOS? <Link to="/register">Create an account</Link>
          </p>

          <small className="auth-security-note">
            The browser talks only to the LifeOS API. Database and AI credentials stay on the backend.
          </small>
        </div>
      </main>
    </div>
  );
}
