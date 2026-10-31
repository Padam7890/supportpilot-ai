"use client";

import Link from "next/link";
import { Suspense } from "react";
import { useParams, useRouter } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { ApiError } from "@/lib/api/errors";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { acceptInvitation, previewInvitation } from "../api/auth-api";
import { inviteAcceptanceSchema } from "../schemas/auth.schema";

export default function InvitePage() {
  return <Suspense fallback={<main className="flex min-h-screen items-center justify-center bg-slate-50 px-4"><div className="h-64 w-full max-w-md animate-pulse rounded-3xl bg-white" /></main>}><InviteContent /></Suspense>;
}

function InviteContent() {
  const { token } = useParams<{ token: string }>();
  const router = useRouter();
  const invitation = useQuery({ queryKey: ["invite-preview", token], queryFn: () => previewInvitation(token) });
  const form = useForm({ resolver: zodResolver(inviteAcceptanceSchema) });
  const accept = useMutation({
    mutationFn: (values: { full_name: string; password: string }) => acceptInvitation(token, values),
    onSuccess: () => router.replace("/dashboard"),
  });
  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-10">
      <section className="w-full max-w-md rounded-3xl border border-slate-200 bg-white p-8 shadow-xl shadow-slate-200/50">
        <Link href="/" className="mb-8 flex items-center gap-3"><span className="flex size-10 items-center justify-center rounded-2xl bg-blue-700 font-black text-white">S</span><span className="font-bold">SupportPilot</span></Link>
        <p className="text-xs font-bold uppercase tracking-[0.16em] text-blue-700">Team invitation</p>
        {invitation.isPending ? <div className="mt-4 h-24 animate-pulse rounded-xl bg-slate-100"/> : invitation.isError || !invitation.data ? <div role="alert" className="mt-4 rounded-xl bg-red-50 p-4 text-sm text-red-700">This invitation is invalid, expired, or has already been used.</div> : <>
          <h1 className="mt-2 text-2xl font-bold">Join {invitation.data.organization_name}</h1>
          <p className="mt-2 text-sm text-slate-500">You’ve been invited as a {invitation.data.role}. Create your account to join the team.</p>
          <p className="mt-4 rounded-xl bg-slate-50 p-3 text-sm text-slate-700">{invitation.data.email}</p>
          <form className="mt-5 space-y-4" onSubmit={form.handleSubmit((values) => accept.mutate(values))}>
            <Field label="Full name" error={form.formState.errors.full_name?.message}><Input autoComplete="name" {...form.register("full_name")}/></Field>
            <Field label="Create a password" error={form.formState.errors.password?.message}><Input type="password" autoComplete="new-password" {...form.register("password")}/></Field>
            {accept.isError && <p role="alert" className="text-sm text-red-700">{accept.error instanceof ApiError ? accept.error.message : "Unable to accept invitation."}</p>}
            <Button className="w-full" type="submit" disabled={accept.isPending}>{accept.isPending ? "Joining…" : "Join workspace"}</Button>
          </form>
        </>}
      </section>
    </main>
  );
}

function Field({ label, error, children }: { label: string; error?: string; children: React.ReactNode }) {
  return <label className="block space-y-1.5 text-sm font-medium text-slate-700"><span>{label}</span>{children}{error && <span className="block text-xs font-normal text-red-600">{error}</span>}</label>;
}
