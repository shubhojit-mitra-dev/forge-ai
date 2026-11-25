"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { z } from "zod";
import { createClient } from "@/lib/supabase/client";
import { cn } from "@/lib/utils";

const AuthSchema = z.object({
  email: z.string().trim().email("Enter a valid email address."),
  password: z
    .string()
    .min(6, "Password must be at least 6 characters."),
});

type AuthMode = "signin" | "signup";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<AuthMode>("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setNotice(null);

    const parsed = AuthSchema.safeParse({ email, password });
    if (!parsed.success) {
      setError(parsed.error.issues[0]?.message ?? "Invalid credentials.");
      return;
    }

    setIsSubmitting(true);
    try {
      const supabase = createClient();

      if (mode === "signin") {
        const { error: signInError } = await supabase.auth.signInWithPassword({
          email: parsed.data.email,
          password: parsed.data.password,
        });
        if (signInError) {
          setError(signInError.message);
          return;
        }
        router.push("/");
        router.refresh();
        return;
      }

      const { data, error: signUpError } = await supabase.auth.signUp({
        email: parsed.data.email,
        password: parsed.data.password,
      });

      if (signUpError) {
        setError(signUpError.message);
        return;
      }

      if (data.session) {
        router.push("/");
        router.refresh();
        return;
      }

      setNotice(
        "Account created. Check your inbox to confirm your email before signing in.",
      );
      setMode("signin");
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Authentication service is unavailable.",
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen bg-canvas text-ink flex flex-col justify-between px-6 py-10">
      <header className="max-w-5xl w-full mx-auto flex items-center justify-between">
        <Link
          href="/"
          className="font-sans font-bold tracking-tight text-xl text-ink"
        >
          FORGE\AI
        </Link>
        <span className="font-mono text-xs uppercase tracking-widest text-text-tertiary">
          Agent Factory
        </span>
      </header>

      <main className="max-w-md w-full mx-auto my-auto py-12">
        <div className="bg-surface-secondary border border-surface-warm rounded-[16px] p-8">
          <p className="font-mono text-xs uppercase tracking-widest text-text-muted mb-3">
            {mode === "signin" ? "Workspace Access" : "New Operator"}
          </p>
          <h1 className="font-serif font-normal text-3xl leading-tight text-ink mb-2">
            {mode === "signin"
              ? "Sign in to ForgeAI"
              : "Create your ForgeAI account"}
          </h1>
          <p className="font-serif text-base text-text-muted mb-8">
            {mode === "signin"
              ? "Return to your agent specifications, eval runs, and iteration logs."
              : "Start forging grounded, evaluated agents from your own documents."}
          </p>

          <div
            role="tablist"
            aria-label="Authentication mode"
            className="grid grid-cols-2 gap-1 p-1 bg-canvas border border-hairline rounded-[8px] mb-6"
          >
            <button
              type="button"
              role="tab"
              aria-selected={mode === "signin"}
              onClick={() => {
                setMode("signin");
                setError(null);
                setNotice(null);
              }}
              className={cn(
                "py-2 text-sm font-medium rounded-[6px] transition-colors cursor-pointer",
                mode === "signin"
                  ? "bg-ink text-canvas"
                  : "text-text-muted hover:text-ink",
              )}
            >
              Sign in
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={mode === "signup"}
              onClick={() => {
                setMode("signup");
                setError(null);
                setNotice(null);
              }}
              className={cn(
                "py-2 text-sm font-medium rounded-[6px] transition-colors cursor-pointer",
                mode === "signup"
                  ? "bg-ink text-canvas"
                  : "text-text-muted hover:text-ink",
              )}
            >
              Sign up
            </button>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5" noValidate>
            <div>
              <label
                htmlFor="email"
                className="block font-sans text-xs font-medium text-ink mb-1.5"
              >
                Email
              </label>
              <input
                id="email"
                name="email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@company.com"
                className="w-full h-11 px-4 bg-canvas text-ink font-sans text-[15px] rounded-[8px] border border-text-secondary placeholder:text-text-tertiary focus:outline-none focus:border-ink transition-colors"
              />
            </div>

            <div>
              <label
                htmlFor="password"
                className="block font-sans text-xs font-medium text-ink mb-1.5"
              >
                Password
              </label>
              <input
                id="password"
                name="password"
                type="password"
                autoComplete={
                  mode === "signin" ? "current-password" : "new-password"
                }
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="At least 6 characters"
                className="w-full h-11 px-4 bg-canvas text-ink font-sans text-[15px] rounded-[8px] border border-text-secondary placeholder:text-text-tertiary focus:outline-none focus:border-ink transition-colors"
              />
            </div>

            {error ? (
              <div
                role="alert"
                className="px-3.5 py-2.5 rounded-[8px] border border-accent-fig bg-canvas text-sm text-ink"
              >
                <span className="font-mono text-[11px] uppercase tracking-wider text-accent-fig mr-2">
                  Error
                </span>
                {error}
              </div>
            ) : null}

            {notice ? (
              <div
                role="status"
                className="px-3.5 py-2.5 rounded-[8px] border border-accent-olive bg-canvas text-sm text-ink"
              >
                <span className="font-mono text-[11px] uppercase tracking-wider text-accent-olive mr-2">
                  Sent
                </span>
                {notice}
              </div>
            ) : null}

            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full h-11 px-6 bg-ink text-canvas font-serif text-base font-semibold rounded-[16px] hover:opacity-90 disabled:opacity-50 transition-opacity cursor-pointer disabled:cursor-not-allowed"
            >
              {isSubmitting
                ? mode === "signin"
                  ? "Signing in..."
                  : "Creating account..."
                : mode === "signin"
                  ? "Sign in"
                  : "Create account"}
            </button>
          </form>
        </div>
      </main>

      <footer className="max-w-5xl w-full mx-auto flex items-center justify-between border-t border-hairline pt-6 text-xs text-text-tertiary">
        <span>ForgeAI Workspace</span>
        <Link href="/" className="text-ink underline underline-offset-4">
          Back to workspace
        </Link>
      </footer>
    </div>
  );
}
