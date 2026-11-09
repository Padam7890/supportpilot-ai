"use client";

import { useState, type ReactNode } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEditor, EditorContent, type JSONContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Bold, Heading2, Italic, Link2, List, ListOrdered, LoaderCircle, Quote, Save, Strikethrough } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input, Select, Textarea } from "@/components/ui/input";
import { ApiError } from "@/lib/api/errors";
import { currentUserQueryKey, getCurrentUser } from "@/features/auth/api/auth-api";
import { knowledgeBaseKey, listKnowledgeBases } from "../api/knowledge-base-api";
import { knowledgeKeys, uploadKnowledgeDocument } from "../api/knowledge-api";

export function KnowledgeArticleEditor() {
  const router = useRouter();
  const client = useQueryClient();
  const [title, setTitle] = useState("");
  const [summary, setSummary] = useState("");
  const [contentLength, setContentLength] = useState(0);
  const [baseId, setBaseId] = useState("");
  const [error, setError] = useState("");
  const user = useQuery({ queryKey: currentUserQueryKey, queryFn: getCurrentUser });
  const bases = useQuery({ queryKey: knowledgeBaseKey, queryFn: listKnowledgeBases });
  const activeBases = bases.data?.items.filter((base) => base.status === "active") ?? [];
  const effectiveBaseId = activeBases.some((base) => base.id === baseId) ? baseId : activeBases.find((base) => base.is_default)?.id ?? activeBases[0]?.id ?? "";
  const editor = useEditor({
    extensions: [StarterKit],
    immediatelyRender: false,
    content: "",
    editorProps: { attributes: { "aria-label": "Article content", class: "outline-none" } },
    onUpdate: ({ editor: updated }) => {
      const length = updated.getText().length;
      setContentLength(length);
      setError(length > 50_000 ? "Keep the article under 50,000 characters." : "");
    },
  });

  const saveArticle = useMutation({
    mutationFn: async () => {
      const cleanTitle = title.trim();
      if (!cleanTitle || !editor || !editor.getText().trim() || !effectiveBaseId) throw new Error("Add an article title, content, and library first.");
      if (editor.getText().length > 50_000) throw new Error("Keep the article under 50,000 characters.");
      const markdown = `${summary.trim() ? `> ${summary.trim()}\n\n` : ""}${toMarkdown(editor.getJSON())}`;
      const safeName = cleanTitle.replace(/[\\/:*?"<>|]/g, "-").replace(/\s+/g, " ").slice(0, 180).trim() || "Knowledge article";
      return uploadKnowledgeDocument({ file: new File([markdown], `${safeName}.md`, { type: "text/markdown" }), knowledgeBaseId: effectiveBaseId });
    },
    onSuccess: async (document) => {
      await Promise.all([client.invalidateQueries({ queryKey: knowledgeKeys.documents }), client.invalidateQueries({ queryKey: knowledgeBaseKey })]);
      router.push(`/dashboard/knowledge/${document.id}`);
    },
    onError: (reason) => {
      if (reason instanceof ApiError && reason.correlationId) {
        setError(`${reason.message} Reference: ${reason.correlationId}`);
        return;
      }
      setError(reason instanceof Error ? reason.message : "The article could not be added.");
    },
  });

  if (!user.isPending && user.data && !["owner", "admin"].includes(user.data.role)) {
    return <div className="-m-3 min-h-[calc(100dvh-3.25rem)] bg-background px-6 py-10 text-foreground sm:-m-5 lg:-m-6"><p className="mx-auto max-w-2xl rounded-xl border border-border bg-muted p-5 text-sm text-muted-foreground">Your role has read-only access to knowledge settings. <Link href="/dashboard/knowledge" className="ml-1 text-primary underline">Back to knowledge</Link></p></div>;
  }

  return <div className="-m-3 min-h-[calc(100dvh-3.25rem)] bg-background text-foreground sm:-m-5 lg:-m-6">
    <header className="flex min-h-[58px] items-center justify-between gap-4 border-b border-border px-6 py-3">
      <div className="flex min-w-0 items-center gap-3"><Link href="/dashboard/knowledge" aria-label="Back to knowledge bases" className="rounded-md p-2 text-muted-foreground hover:bg-accent hover:text-foreground"><ArrowLeft size={17}/></Link><div className="min-w-0"><h1 className="truncate text-sm font-semibold">{title.trim() || "New article"}</h1><p className="text-xs text-muted-foreground">New source · saved when added to a library</p></div></div>
      <Button onClick={() => { setError(""); saveArticle.mutate(); }} disabled={saveArticle.isPending || !title.trim() || contentLength === 0 || !effectiveBaseId} className="h-9 bg-primary px-4 text-primary-foreground hover:bg-primary-hover">{saveArticle.isPending ? <LoaderCircle className="animate-spin" size={15}/> : <Save size={15}/>}Add to library</Button>
    </header>
    <div className="mx-auto grid max-w-[1180px] gap-10 px-6 py-10 lg:grid-cols-[minmax(0,1fr)_280px] lg:px-10">
      <section className="min-w-0">
        <Input aria-label="Article title" maxLength={180} value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Article title" className="h-auto border-0 bg-transparent px-0 py-2 text-4xl font-semibold tracking-tight text-foreground shadow-none placeholder:text-muted-foreground focus-visible:border-transparent focus-visible:ring-0"/>
        <div className="mt-5 inline-flex flex-wrap items-center gap-1 rounded-lg border border-border bg-card p-1" role="toolbar" aria-label="Article formatting">
          <ToolbarButton label="Heading" active={editor?.isActive("heading", { level: 2 }) ?? false} onClick={() => editor?.chain().focus().toggleHeading({ level: 2 }).run()}><Heading2 size={16}/></ToolbarButton>
          <ToolbarButton label="Bold" active={editor?.isActive("bold") ?? false} onClick={() => editor?.chain().focus().toggleBold().run()}><Bold size={15}/></ToolbarButton>
          <ToolbarButton label="Italic" active={editor?.isActive("italic") ?? false} onClick={() => editor?.chain().focus().toggleItalic().run()}><Italic size={15}/></ToolbarButton>
          <ToolbarButton label="Strikethrough" active={editor?.isActive("strike") ?? false} onClick={() => editor?.chain().focus().toggleStrike().run()}><Strikethrough size={15}/></ToolbarButton>
          <ToolbarButton label="Bulleted list" active={editor?.isActive("bulletList") ?? false} onClick={() => editor?.chain().focus().toggleBulletList().run()}><List size={16}/></ToolbarButton>
          <ToolbarButton label="Numbered list" active={editor?.isActive("orderedList") ?? false} onClick={() => editor?.chain().focus().toggleOrderedList().run()}><ListOrdered size={16}/></ToolbarButton>
          <ToolbarButton label="Quote" active={editor?.isActive("blockquote") ?? false} onClick={() => editor?.chain().focus().toggleBlockquote().run()}><Quote size={15}/></ToolbarButton>
          <ToolbarButton label="Link" active={editor?.isActive("link") ?? false} onClick={() => {
            if (!editor) return;
            const href = window.prompt("Link URL", editor.getAttributes("link").href ?? "https://");
            if (href === null) return;
            if (!href.trim()) editor.chain().focus().unsetLink().run();
            else if (/^https:\/\//i.test(href.trim())) editor.chain().focus().extendMarkRange("link").setLink({ href: href.trim() }).run();
          }}><Link2 size={15}/></ToolbarButton>
        </div>
        <div className="relative mt-4 min-h-[55vh] px-1 py-2 [&_.tiptap]:min-h-[52vh] [&_.tiptap]:outline-none [&_.tiptap]:text-base [&_.tiptap]:leading-8 [&_.tiptap_p]:my-3 [&_.tiptap_h2]:mt-8 [&_.tiptap_h2]:text-2xl [&_.tiptap_h2]:font-semibold [&_.tiptap_h3]:mt-6 [&_.tiptap_h3]:text-xl [&_.tiptap_h3]:font-semibold [&_.tiptap_ul]:my-3 [&_.tiptap_ul]:list-disc [&_.tiptap_ul]:pl-6 [&_.tiptap_ol]:my-3 [&_.tiptap_ol]:list-decimal [&_.tiptap_ol]:pl-6 [&_.tiptap_blockquote]:my-4 [&_.tiptap_blockquote]:border-l-2 [&_.tiptap_blockquote]:border-primary [&_.tiptap_blockquote]:pl-4 [&_.tiptap_blockquote]:text-muted-foreground [&_.tiptap_a]:text-primary [&_.tiptap_a]:underline">
          <EditorContent editor={editor} />
          {!contentLength && <p className="pointer-events-none absolute left-5 top-4 text-base leading-8 text-muted-foreground">Start writing. Explain the policy, steps, or answer your AI bot should know…</p>}
        </div>
        <p className="mt-2 text-xs text-muted-foreground">{contentLength.toLocaleString()}/50,000 characters · Rich text formatting is supported.</p>
        {bases.isError && <p role="alert" className="mt-4 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">Knowledge libraries could not be loaded: {bases.error instanceof Error ? bases.error.message : "Please try again."} {bases.error instanceof ApiError && bases.error.status === 401 && <Link href="/login" className="underline">Sign in again</Link>}</p>}
        {error && <p role="alert" className="mt-4 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>}
      </section>
      <aside className="space-y-5">
        <label className="block space-y-2 text-xs font-medium text-muted-foreground"><span>Library</span><Select aria-label="Article library" value={effectiveBaseId} onChange={(event) => setBaseId(event.target.value)} disabled={bases.isPending || !activeBases.length} className="h-10 w-full border-border bg-card text-sm text-foreground">{activeBases.map((base) => <option key={base.id} value={base.id}>{base.name}{base.is_default ? " (default)" : ""}</option>)}</Select></label>
        <label className="block space-y-2 text-xs font-medium text-muted-foreground"><span>Summary</span><Textarea maxLength={1000} rows={4} value={summary} onChange={(event) => setSummary(event.target.value)} placeholder="One line on what this covers" className="min-h-24 resize-y border-border bg-card text-sm leading-6 text-foreground placeholder:text-muted-foreground"/></label>
        <div className="rounded-xl border border-border bg-card p-4 text-xs leading-5 text-muted-foreground">When added, this article is processed so bots assigned to <span className="font-medium text-foreground">{activeBases.find((base) => base.id === effectiveBaseId)?.name ?? "the selected library"}</span> can use it. You can edit or reprocess it later from its document page.</div>
      </aside>
    </div>
  </div>;
}

function ToolbarButton({ label, active, onClick, children }: { label: string; active: boolean; onClick: () => void; children: ReactNode }) {
  return <button type="button" aria-label={label} aria-pressed={active} onClick={onClick} className={`rounded-md p-2 transition-colors hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${active ? "bg-accent text-foreground" : "text-muted-foreground"}`}>{children}</button>;
}

function toMarkdown(node: JSONContent): string {
  const children = node.content?.map(toMarkdown) ?? [];
  if (node.type === "text") {
    let text = node.text ?? "";
    for (const mark of node.marks ?? []) {
      if (mark.type === "bold") text = `**${text}**`;
      if (mark.type === "italic") text = `*${text}*`;
      if (mark.type === "strike") text = `~~${text}~~`;
      if (mark.type === "code") text = `\`${text}\``;
      if (mark.type === "link" && typeof mark.attrs?.href === "string") text = `[${text}](${mark.attrs.href})`;
    }
    return text;
  }
  if (node.type === "doc") return children.join("\n\n");
  if (node.type === "paragraph") return children.join("");
  if (node.type === "heading") {
    const level = typeof node.attrs?.level === "number" ? Math.min(6, Math.max(1, node.attrs.level)) : 2;
    return `${"#".repeat(level)} ${children.join("")}`;
  }
  if (node.type === "bulletList") return children.map((item) => item.split("\n").map((line) => `- ${line}`).join("\n")).join("\n");
  if (node.type === "orderedList") {
    const start = typeof node.attrs?.start === "number" ? node.attrs.start : 1;
    return children.map((item, index) => item.split("\n").map((line, lineIndex) => `${lineIndex === 0 ? `${start + index}. ` : "   "}${line}`).join("\n")).join("\n");
  }
  if (node.type === "listItem") return children.join("\n");
  if (node.type === "blockquote") return children.join("\n\n").split("\n").map((line) => `> ${line}`).join("\n");
  if (node.type === "codeBlock") return `\`\`\`\n${children.join("")}\n\`\`\``;
  if (node.type === "hardBreak") return "\n";
  if (node.type === "horizontalRule") return "---";
  return children.join("");
}
