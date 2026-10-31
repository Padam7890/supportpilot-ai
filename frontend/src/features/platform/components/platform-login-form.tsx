"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

import { ApiError } from "@/lib/api/errors";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { FormField } from "@/components/forms/form-field";
import { platformLogin } from "../api/platform-api";
import { platformLoginSchema, type PlatformLoginValues } from "../schemas/platform-auth.schema";

export default function PlatformLoginForm() {
  const router = useRouter();
  const [error, setError] = useState("");
  const form = useForm<PlatformLoginValues>({ resolver: zodResolver(platformLoginSchema) });

  async function onSubmit(values: PlatformLoginValues) {
    setError("");
    try {
      await platformLogin(values);
      router.replace("/platform/tenants");
      router.refresh();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Unable to connect. Please try again.");
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-10">
      <section className="w-full max-w-md rounded-3xl border border-slate-200 bg-white p-8 shadow-xl">
        <Link href="/" className="font-bold text-blue-800">SupportPilot</Link>
        <p className="mt-8 text-xs font-bold uppercase tracking-[0.16em] text-blue-700">Platform administration</p>
        <h1 className="mt-2 text-2xl font-bold">Platform owner sign in</h1>
        <p className="mt-2 text-sm text-slate-500">This sign in is separate from tenant workspaces.</p>
        <form className="mt-6 space-y-4" onSubmit={form.handleSubmit(onSubmit)}>
          <FormField label="Platform owner email" error={form.formState.errors.email?.message}>
            <Input type="email" autoComplete="username" {...form.register("email")} />
          </FormField>
          <FormField label="Password" error={form.formState.errors.password?.message}>
            <Input type="password" autoComplete="current-password" {...form.register("password")} />
          </FormField>
          {error && <p role="alert" className="rounded-xl bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
          <Button className="w-full" type="submit" disabled={form.formState.isSubmitting}>
            {form.formState.isSubmitting ? "Signing in…" : "Sign in to platform"}
          </Button>
        </form>
      </section>
    </main>
  );
}
