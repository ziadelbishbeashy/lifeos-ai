import { FormEvent, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { register, sessionQueryKey } from "../auth/session";

export function RegisterPage() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: register,
    onSuccess: (session) => {
      queryClient.setQueryData(sessionQueryKey, session);
      navigate("/dashboard", { replace: true });
    },
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    mutation.mutate({
      name,
      email,
      password,
      confirm_password: confirmPassword,
    });
  }

  const errorMessage = mutation.error instanceof ApiError
    ? mutation.error.message
    : mutation.isError
      ? "LifeOS could not create the account. Please try again."
      : null;

  return (
    <div className="auth-page">
      <section className="auth-story">
        <Link className="auth-brand" to="/register">
          <span className="brand-mark">L</span>
          <span><strong>LifeOS AI</strong><small>Execution Intelligence</small></span>
        </Link>

        <div className="auth-story-copy">
          <span className="eyebrow">Build one connected workspace</span>
          <h1>Organize work. Keep context. <em>Execute intelligently.</em></h1>
          <p>
            Start with projects and tasks, then let LifeOS connect notes,
            documents and grounded AI around the work you actually own.
          </p>
        </div>
      </section>

      <main className="auth-panel">
        <div className="auth-card">
          <span className="eyebrow">Get started</span>
          <h2>Create your LifeOS account</h2>
          <p className="auth-card-lead">Your existing backend account rules are preserved.</p>

          {errorMessage && <div className="form-alert error">{errorMessage}</div>}

          <form onSubmit={submit} className="auth-form">
            <label>
              <span>Full name</span>
              <input value={name} onChange={(event) => setName(event.target.value)} autoComplete="name" required />
            </label>
            <label>
              <span>Email</span>
              <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" required />
            </label>
            <label>
              <span>Password</span>
              <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="new-password" minLength={8} required />
            </label>
            <label>
              <span>Confirm password</span>
              <input type="password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} autoComplete="new-password" minLength={8} required />
            </label>

            <button className="primary-button auth-submit" type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? "Creating workspace…" : "Create account"}
            </button>
          </form>

          <p className="auth-switch">
            Already have an account? <Link to="/login">Log in</Link>
          </p>
        </div>
      </main>
    </div>
  );
}
