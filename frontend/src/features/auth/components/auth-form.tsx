"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { ApiError } from "@/lib/api/errors";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  completePasswordReset,
  login as loginRequest,
  register as registerRequest,
  requestPasswordReset,
  resendAuthCode,
  selectLoginWorkspace,
  verifyLoginCode,
  verifyRegistrationCode,
  type WorkspaceChoice,
} from "../api/auth-api";
import { loginSchema, registerSchema, type LoginValues, type RegisterValues } from "../schemas/auth.schema";
import { organizationSlugFromName } from "../utils/organization-slug";

type FlowStep =
  | "credentials"
  | "workspace"
  | "login-code"
  | "registration-code"
  | "recovery-email"
  | "recovery-code";

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const router = useRouter();
  const [step, setStep] = useState<FlowStep>(mode === "login" ? "credentials" : "credentials");
  const [message, setMessage] = useState("");
  const [notice, setNotice] = useState("");
  const [workspaces, setWorkspaces] = useState<WorkspaceChoice[]>([]);
  const [emailHint, setEmailHint] = useState("");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [slugEdited, setSlugEdited] = useState(false);
  const [sendingWorkspaceId, setSendingWorkspaceId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const login = useForm<LoginValues>({ resolver: zodResolver(loginSchema) });
  const register = useForm<RegisterValues>({ resolver: zodResolver(registerSchema) });
  const { clearErrors, getValues, setValue } = register;
  const organizationName = useWatch({ control: register.control, name: "organization_name" });

  useEffect(() => {
    if (mode !== "register" || slugEdited) return;
    setValue("organization_slug", organizationSlugFromName(organizationName ?? ""), {
      shouldDirty: true,
    });
    clearErrors("organization_slug");
  }, [clearErrors, mode, organizationName, setValue, slugEdited]);

  async function run(action: () => Promise<void>) {
    setMessage("");
    setNotice("");
    setBusy(true);
    try {
      await action();
    } catch (error) {
      if (
        mode === "register" &&
        error instanceof ApiError &&
        error.status === 409 &&
        /slug/i.test(error.message)
      ) {
        register.setError("organization_slug", {
          type: "server",
          message: "This workspace address is already in use. Choose another one.",
        });
      } else if (error instanceof ApiError && error.status >= 500) {
        setMessage(
          "Sign-in service is unavailable. Check /api/health/ready and the backend log for migration or email-delivery errors.",
        );
      } else {
        setMessage(error instanceof ApiError ? error.message : "Unable to connect. Please try again.");
      }
    } finally {
      setBusy(false);
    }
  }

  const submitLogin = login.handleSubmit((values) => run(async () => {
    const result = await loginRequest(values);
    if ("user" in result) {
      router.replace("/dashboard");
      router.refresh();
      return;
    }
    setEmail(values.email);
    setEmailHint(result.email_hint ?? values.email);
    if (result.status === "workspace_selection_required") {
      setWorkspaces(result.workspaces);
      setStep("workspace");
      return;
    }
    setStep("login-code");
  }));

  const submitRegistration = register.handleSubmit((values) => run(async () => {
    await registerRequest(values);
    setEmail(values.email);
    setEmailHint(values.email);
    setStep("registration-code");
    setNotice(`We sent a verification code to ${values.email}.`);
  }));

  async function chooseWorkspace(workspace: WorkspaceChoice) {
    if (busy) return;
    setSendingWorkspaceId(workspace.membership_id);
    try {
      await run(async () => {
        const result = await selectLoginWorkspace(workspace.membership_id);
        if ("user" in result) {
          router.replace("/dashboard");
          router.refresh();
          return;
        }
        setEmailHint(result.email_hint ?? email);
        setStep("login-code");
      });
    } finally {
      setSendingWorkspaceId(null);
    }
  }

  async function submitLoginCode(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await run(async () => {
      await verifyLoginCode(code);
      router.replace("/dashboard");
      router.refresh();
    });
  }

  async function submitRegistrationCode(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await run(async () => {
      await verifyRegistrationCode(code);
      router.replace("/register/pending");
      router.refresh();
    });
  }

  async function submitRecoveryRequest(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await run(async () => {
      const result = await requestPasswordReset(email);
      setStep("recovery-code");
      setNotice(result.message);
    });
  }

  async function submitRecoveryCode(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await run(async () => {
      await completePasswordReset(code, newPassword);
      setStep("credentials");
      setCode("");
      setNewPassword("");
      setNotice("Password updated. Sign in with your new password.");
    });
  }

  async function resendCode() {
    await run(async () => {
      const result = await resendAuthCode();
      setNotice(result.message);
    });
  }

  if (mode === "login" && step === "workspace") {
    return (
      <section aria-labelledby="workspace-choice-heading" className="space-y-4">
        <div>
          <h2 id="workspace-choice-heading" className="text-lg font-semibold text-slate-900">Choose a workspace</h2>
          <p className="mt-1 text-sm text-slate-500">Your account has access to multiple approved workspaces.</p>
        </div>
        <div className="space-y-2">
          {workspaces.map((workspace) => (
            <Button variant="unstyled"
              key={workspace.membership_id}
              type="button"
              disabled={busy}
              onClick={() => void chooseWorkspace(workspace)}
              className="flex w-full items-center justify-between rounded-xl border border-slate-200 px-4 py-3 text-left transition hover:border-blue-400 hover:bg-blue-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700 disabled:opacity-60"
            >
              <span>
                <span className="block font-semibold text-slate-900">{workspace.organization_name}</span>
                <span className="block text-sm text-slate-500">{workspace.organization_slug}</span>
              </span>
              <span className="text-sm font-semibold text-blue-700">
                {sendingWorkspaceId === workspace.membership_id ? "Sending…" : "Continue"}
              </span>
            </Button>
          ))}
        </div>
        <FlowMessages error={message} notice={notice} />
        <Button variant="unstyled" type="button" className="text-sm font-semibold text-blue-700 hover:underline" onClick={() => setStep("credentials")}>Back to sign in</Button>
      </section>
    );
  }

  if (mode === "login" && step === "login-code") {
    return (
      <OtpPanel
        title="Verify it’s you"
        description={`Enter the 6-digit code we sent to ${emailHint || email}. The code expires in 10 minutes.`}
        code={code}
        busy={busy}
        error={message}
        notice={notice}
        onCodeChange={setCode}
        onSubmit={submitLoginCode}
        onResend={() => void resendCode()}
        onBack={() => setStep("credentials")}
      />
    );
  }

  if (mode === "register" && step === "registration-code") {
    return (
      <OtpPanel
        title="Verify your email"
        description={`Enter the 6-digit code sent to ${emailHint}. We’ll submit your workspace for owner review after verification.`}
        code={code}
        busy={busy}
        error={message}
        notice={notice}
        onCodeChange={setCode}
        onSubmit={submitRegistrationCode}
        onResend={() => void resendCode()}
      />
    );
  }

  if (mode === "login" && step === "recovery-email") {
    return (
      <form className="space-y-4" onSubmit={submitRecoveryRequest}>
        <h2 className="text-lg font-semibold text-slate-900">Reset your password</h2>
        <p className="text-sm text-slate-500">We’ll send a verification code if this email can recover a SupportPilot account.</p>
        <Field label="Work email"><Input type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} /></Field>
        <FlowMessages error={message} notice={notice} />
        <Button className="w-full" type="submit" disabled={busy}>{busy ? "Sending…" : "Send recovery code"}</Button>
        <Button variant="unstyled" type="button" className="w-full text-sm font-semibold text-blue-700 hover:underline" onClick={() => setStep("credentials")}>Back to sign in</Button>
      </form>
    );
  }

  if (mode === "login" && step === "recovery-code") {
    return (
      <form className="space-y-4" onSubmit={submitRecoveryCode}>
        <h2 className="text-lg font-semibold text-slate-900">Choose a new password</h2>
        <p className="text-sm text-slate-500">Enter the code sent to {email}. Codes expire after 10 minutes.</p>
        <Field label="Verification code"><Input inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} required value={code} onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))} /></Field>
        <Field label="New password"><Input type="password" autoComplete="new-password" minLength={12} maxLength={128} required value={newPassword} onChange={(event) => setNewPassword(event.target.value)} /></Field>
        <FlowMessages error={message} notice={notice} />
        <Button className="w-full" type="submit" disabled={busy || code.length !== 6}>{busy ? "Updating…" : "Update password"}</Button>
        <Button variant="unstyled" type="button" className="w-full text-sm font-semibold text-blue-700 hover:underline" onClick={() => void resendCode()}>Resend code</Button>
      </form>
    );
  }

  return (
    <form className="space-y-4" onSubmit={mode === "login" ? submitLogin : submitRegistration}>
      {mode === "register" && <>
        <Field label="Organization name" error={register.formState.errors.organization_name?.message}>
          <Input
            autoComplete="organization"
            {...register.register("organization_name")}
          />
        </Field>
        <Field label="Organization slug" error={register.formState.errors.organization_slug?.message}>
          <Input
            autoComplete="off"
            placeholder="acme-support"
            aria-describedby="organization-slug-hint"
            {...register.register("organization_slug", {
              onChange: (event) => {
                setSlugEdited(
                  event.target.value !== organizationSlugFromName(getValues("organization_name") ?? ""),
                );
              },
            })}
          />
          <span id="organization-slug-hint" className="block text-xs font-normal text-slate-500">
            Suggested from your organization name. You can edit it; workspace addresses must be unique.
          </span>
        </Field>
        <Field label="Your name" error={register.formState.errors.full_name?.message}>
          <Input autoComplete="name" {...register.register("full_name")} />
        </Field>
      </>}
      <Field label="Work email" error={mode === "login" ? login.formState.errors.email?.message : register.formState.errors.email?.message}>
        <Input
          type="email"
          autoComplete="email"
          {...(mode === "login" ? login.register("email") : register.register("email"))}
        />
      </Field>
      <Field label={mode === "login" ? "Password" : "Create a password"} error={mode === "login" ? login.formState.errors.password?.message : register.formState.errors.password?.message}>
        <Input
          type="password"
          autoComplete={mode === "login" ? "current-password" : "new-password"}
          {...(mode === "login" ? login.register("password") : register.register("password"))}
        />
      </Field>
      <FlowMessages error={message} notice={notice} />
      <Button className="w-full" type="submit" disabled={busy || (mode === "login" ? login.formState.isSubmitting : register.formState.isSubmitting)}>
        {busy ? "Please wait…" : mode === "login" ? "Continue" : "Submit for approval"}
      </Button>
      {mode === "login" && <Button variant="unstyled" type="button" className="w-full text-sm font-semibold text-blue-700 hover:underline" onClick={() => {
        setEmail(login.getValues("email") ?? "");
        setStep("recovery-email");
        setMessage("");
        setNotice("");
      }}>Forgot password?</Button>}
      <p className="text-center text-sm text-slate-500">
        {mode === "login" ? "New to SupportPilot? " : "Already have a workspace? "}
        <Link className="font-semibold text-blue-700 hover:underline" href={mode === "login" ? "/register" : "/login"}>
          {mode === "login" ? "Create an account" : "Sign in"}
        </Link>
      </p>
    </form>
  );
}

function OtpPanel({
  title,
  description,
  code,
  busy,
  error,
  notice,
  onCodeChange,
  onSubmit,
  onResend,
  onBack,
}: {
  title: string;
  description: string;
  code: string;
  busy: boolean;
  error: string;
  notice: string;
  onCodeChange: (code: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onResend: () => void;
  onBack?: () => void;
}) {
  return (
    <form className="space-y-4" onSubmit={onSubmit}>
      <div><h2 className="text-lg font-semibold text-slate-900">{title}</h2><p className="mt-1 text-sm leading-6 text-slate-500">{description}</p></div>
      <Field label="6-digit verification code">
        <Input
          inputMode="numeric"
          autoComplete="one-time-code"
          pattern="[0-9]{6}"
          maxLength={6}
          required
          autoFocus
          value={code}
          onChange={(event) => onCodeChange(event.target.value.replace(/\D/g, "").slice(0, 6))}
        />
      </Field>
      <FlowMessages error={error} notice={notice} />
      <Button className="w-full" type="submit" disabled={busy || code.length !== 6}>{busy ? "Verifying…" : "Verify and continue"}</Button>
      <Button variant="unstyled" type="button" className="w-full text-sm font-semibold text-blue-700 hover:underline disabled:opacity-60" disabled={busy} onClick={onResend}>Resend code</Button>
      {onBack && <Button variant="unstyled" type="button" className="w-full text-sm text-slate-500 hover:underline" onClick={onBack}>Back</Button>}
    </form>
  );
}

function FlowMessages({ error, notice }: { error: string; notice: string }) {
  return <>
    {error && <p role="alert" className="rounded-xl bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
    {notice && <p role="status" className="rounded-xl bg-blue-50 px-3 py-2 text-sm text-blue-800">{notice}</p>}
  </>;
}

function Field({ label, error, children }: { label: string; error?: string; children: ReactNode }) {
  return (
    <label className="block space-y-2.5 text-sm font-medium text-slate-700">
      <span>{label}</span>
      {children}
      {error && <span className="block text-xs font-normal text-red-600">{error}</span>}
    </label>
  );
}

export function AuthPanel({ mode }: { mode: "login" | "register" }) {
  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-10">
      <section className="w-full max-w-md rounded-3xl border border-slate-200 bg-white p-7 shadow-xl shadow-slate-200/50 sm:p-9">
        <Link href="/" className="mb-8 flex items-center gap-3">
          <span className="flex size-11 items-center justify-center rounded-2xl bg-blue-700 text-lg font-black text-white">S</span>
          <span><span className="block font-bold text-slate-900">SupportPilot</span><span className="text-xs text-slate-500">Customer support workspace</span></span>
        </Link>
        <div className="mb-7">
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-blue-700">{mode === "login" ? "Welcome back" : "Get started"}</p>
          <h1 className="mt-2 text-2xl font-bold tracking-tight text-slate-950">{mode === "login" ? "Sign in to your workspace" : "Request a workspace"}</h1>
          <p className="mt-2 text-sm leading-6 text-slate-500">{mode === "login" ? "Enter your email and password." : "A platform owner will review your workspace after you verify your email."}</p>
        </div>
        <AuthForm mode={mode} />
      </section>
    </main>
  );
}

export function formatAuthError(error: unknown) {
  return error instanceof Error ? error.message : "Something went wrong";
}
