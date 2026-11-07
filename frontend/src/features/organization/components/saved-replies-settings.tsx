"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, MessageSquareText, Plus, Save, Undo2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { FormField } from "@/components/ui/form-field";
import { Input, Textarea } from "@/components/ui/input";
import { StatusAlert } from "@/components/ui/status-alert";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { archiveSavedReply, createSavedReply, listSavedReplies, restoreSavedReply, savedRepliesQueryKey, updateSavedReply, type SavedReply } from "@/features/saved-replies/api/saved-replies-api";

export function SavedRepliesSettings({ organizationId }: { organizationId: string | undefined }) {
  const queryClient = useQueryClient();
  const repliesKey = savedRepliesQueryKey(organizationId);
  const replies = useQuery({ queryKey: repliesKey, queryFn: () => listSavedReplies(true), enabled: Boolean(organizationId) });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected = replies.data?.find((item) => item.id === selectedId);
  const [title, setTitle] = useState("");
  const [shortcut, setShortcut] = useState("");
  const [body, setBody] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  function edit(item: SavedReply) {
    setSelectedId(item.id);
    setTitle(item.title);
    setShortcut(item.shortcut);
    setBody(item.body);
    setFormError(null);
    setSuccessMessage(null);
  }

  function reset(clearStatus = true) {
    setSelectedId(null);
    setTitle("");
    setShortcut("");
    setBody("");
    setFormError(null);
    if (clearStatus) setSuccessMessage(null);
  }

  const save = useMutation({
    mutationFn: () => selectedId
      ? updateSavedReply(selectedId, { title, shortcut, body })
      : createSavedReply({ title, shortcut, body }),
    onSuccess: async () => {
      setSuccessMessage(selectedId ? "Saved reply updated." : "Saved reply created.");
      reset(false);
      await queryClient.invalidateQueries({ queryKey: repliesKey });
    },
    onError: (error: Error) => setFormError(error.message),
  });
  const archive = useMutation({
    mutationFn: archiveSavedReply,
    onSuccess: async () => {
      if (selectedId) reset();
      await queryClient.invalidateQueries({ queryKey: repliesKey });
    },
  });
  const restore = useMutation({
    mutationFn: restoreSavedReply,
    onSuccess: async () => queryClient.invalidateQueries({ queryKey: repliesKey }),
  });

  return <div className="space-y-5">
    <Panel>
      <PanelHeader title="Saved replies" description="Create reusable answers for common customer questions. Replies are inserted into the composer for review; they are never sent automatically." action={<span className="grid size-9 place-items-center rounded-xl bg-blue-50 text-blue-700"><MessageSquareText size={18}/></span>}/>
      <PanelBody className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(320px,0.9fr)]">
        <div>
          <div className="mb-3 flex items-center justify-between gap-3"><h3 className="text-sm font-semibold">Workspace replies</h3><Button type="button" size="sm" variant="secondary" onClick={() => reset()}><Plus size={15}/>New reply</Button></div>
          {replies.isPending ? <div className="h-28 animate-pulse rounded-xl bg-slate-100"/> : replies.isError ? <StatusAlert tone="error" title="Saved replies could not be loaded." onRetry={() => replies.refetch()}>Refresh the list and try again.</StatusAlert> : replies.data?.length ? <ul className="divide-y divide-slate-100 rounded-xl border border-slate-200">{replies.data.map((item) => <li key={item.id} className="flex items-start gap-3 p-3"><button type="button" className="min-w-0 flex-1 text-left" onClick={() => edit(item)}><span className="block truncate text-sm font-semibold text-slate-900">{item.title}{!item.is_active && <span className="ml-2 text-xs font-normal text-slate-500">Archived</span>}</span><span className="mt-0.5 block text-xs text-slate-500">/{item.shortcut}</span><span className="mt-2 line-clamp-2 whitespace-pre-wrap text-xs text-slate-600">{item.body}</span></button>{item.is_active ? <Button type="button" size="sm" variant="ghost" aria-label={`Archive ${item.title}`} disabled={archive.isPending} onClick={() => archive.mutate(item.id)}><Archive size={15}/></Button> : <Button type="button" size="sm" variant="secondary" aria-label={`Restore ${item.title}`} disabled={restore.isPending} onClick={() => restore.mutate(item.id)}><Undo2 size={15}/>Restore</Button>}</li>)}</ul> : <div className="rounded-xl border border-dashed border-slate-300 p-6 text-center"><p className="text-sm font-medium">No saved replies yet</p><p className="mt-1 text-xs text-slate-500">Create an answer your team can reuse from the Inbox.</p></div>}
          {archive.isError && <StatusAlert tone="error" className="mt-2">This reply could not be archived.</StatusAlert>}
          {restore.isError && <StatusAlert tone="error" className="mt-2">This reply could not be restored.</StatusAlert>}
        </div>
        <form className="space-y-3 rounded-xl border border-slate-200 bg-slate-50/70 p-4" onSubmit={(event) => { event.preventDefault(); if (!title.trim() || !shortcut.trim() || !body.trim()) { setFormError("Add a title, shortcut, and reply text."); return; } save.mutate(); }}>
          <h3 className="text-sm font-semibold">{selected ? "Edit saved reply" : "Create saved reply"}</h3>
          <FormField label="Title"><Input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={120} placeholder="Shipping update"/></FormField>
          <FormField label="Shortcut" hint="Letters, numbers, hyphens, and underscores."><div className="flex items-center gap-2"><span className="text-muted-foreground">/</span><Input value={shortcut} onChange={(event) => setShortcut(event.target.value.toLowerCase().replace(/^\//, ""))} maxLength={40} placeholder="shipping-update"/></div></FormField>
          <FormField label="Reply text"><Textarea value={body} onChange={(event) => setBody(event.target.value)} maxLength={5000} rows={6} placeholder="Write a helpful response…"/></FormField>
          {formError && <StatusAlert tone="error">{formError}</StatusAlert>}
          {successMessage && <p role="status" className="text-sm text-emerald-700">{successMessage}</p>}
          <div className="flex flex-wrap gap-2"><Button type="submit" disabled={save.isPending}><Save size={15}/>{save.isPending ? "Saving…" : selected ? "Save changes" : "Create reply"}</Button>{selected && <Button type="button" variant="secondary" onClick={() => reset()}>Cancel</Button>}</div>
        </form>
      </PanelBody>
    </Panel>
    <p className="text-xs text-slate-500">Saved replies are shared with this workspace. Keep customer-specific information out of reusable templates.</p>
  </div>;
}
