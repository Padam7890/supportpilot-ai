"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { ApiError } from "@/lib/api/errors";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useState } from "react";
import { login as loginRequest, register as registerRequest } from "../api/auth-api";
import { loginSchema, registerSchema, type LoginValues, type RegisterValues } from "../schemas/auth.schema";

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const router = useRouter();
  const [message, setMessage] = useState("");
  const login = useForm<LoginValues>({ resolver: zodResolver(loginSchema) });
  const register = useForm<RegisterValues>({ resolver: zodResolver(registerSchema) });
  const emailProps = mode === "login" ? login.register("email") : register.register("email");
  const passwordProps = mode === "login" ? login.register("password") : register.register("password");
  const emailError = mode === "login" ? login.formState.errors.email?.message : register.formState.errors.email?.message;
  const passwordError = mode === "login" ? login.formState.errors.password?.message : register.formState.errors.password?.message;
  const submitting = mode === "login" ? login.formState.isSubmitting : register.formState.isSubmitting;
  const onSubmit = mode === "login"
    ? login.handleSubmit((values) => submit(values))
    : register.handleSubmit((values) => submit(values));
  const submit = async (values: LoginValues | RegisterValues) => {
    setMessage("");
    try {
      if (mode === "login") {
        await loginRequest(values as LoginValues);
        router.replace("/dashboard");
      } else {
        await registerRequest(values as RegisterValues);
        router.replace("/register/pending");
      }
      router.refresh();
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : "Unable to connect. Please try again.");
    }
  };

  return (
    <form className="space-y-4" onSubmit={onSubmit}>
      {mode === "register" && <>
        <Field label="Organization name" error={register.formState.errors.organization_name?.message}>
          <Input autoComplete="organization" {...register.register("organization_name")} />
        </Field>
        <Field label="Organization slug" error={register.formState.errors.organization_slug?.message}>
          <Input autoComplete="off" placeholder="acme-support" {...register.register("organization_slug")} />
        </Field>
        <Field label="Your name" error={register.formState.errors.full_name?.message}>
          <Input autoComplete="name" {...register.register("full_name")} />
        </Field>
      </>}
      {mode === "login" && <Field label="Organization slug" error={login.formState.errors.organization_slug?.message}>
        <Input autoComplete="organization" placeholder="acme-support" {...login.register("organization_slug")} />
      </Field>}
      <Field label="Work email" error={emailError}>
        <Input type="email" autoComplete="email" {...emailProps} />
      </Field>
      <Field label="Password" error={passwordError}>
        <Input type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} {...passwordProps} />
      </Field>
      {message && <p role="alert" className="rounded-xl bg-red-50 px-3 py-2 text-sm text-red-700">{message}</p>}
      <Button className="w-full" type="submit" disabled={submitting}>
        {submitting ? "Please wait…" : mode === "login" ? "Sign in" : "Submit for approval"}
      </Button>
      <p className="text-center text-sm text-slate-500">
        {mode === "login" ? "New to SupportPilot? " : "Already have a workspace? "}
        <Link className="font-semibold text-blue-700 hover:underline" href={mode === "login" ? "/register" : "/login"}>
          {mode === "login" ? "Create an account" : "Sign in"}
        </Link>
      </p>
    </form>
  );
}

function Field({ label, error, children }: { label: string; error?: string; children: React.ReactNode }) {
  return (
    <label className="block space-y-1.5 text-sm font-medium text-slate-700">
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
          <p className="mt-2 text-sm leading-6 text-slate-500">{mode === "login" ? "Pick up where your support team left off." : "A platform owner will review your workspace before sign in is enabled."}</p>
        </div>
        <AuthForm mode={mode} />
      </section>
    </main>
  );
}

export function formatAuthError(error: unknown) {
  return error instanceof Error ? error.message : "Something went wrong";
}
