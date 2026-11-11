"use client";

import { ChevronDown, ChevronLeft, ChevronRight, CircleHelp, Plus, RotateCw, Search } from "lucide-react";
import { useDeferredValue, useEffect, useRef, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import {
  listCustomerQuestions, listQuestionGroups, listQuestionReviews, questionActions, questionKeys,
  type AnswerDraft, type DashboardCounts, type QuestionGroup, type QuestionPeriod, type QuestionView,
} from "../api/knowledge-gap-api";
import { CustomerQuestionAnswerDrawer } from "./customer-question-answer-drawer";
import { CustomerQuestionListItem } from "./customer-question-list";

const pageSize = 50;
const periods = { "7": "Last 7 days", "30": "Last 30 days", "90": "Last 90 days", all: "All time" } satisfies Record<QuestionPeriod, string>;
const views = [
  { id: "all", label: "All questions" }, { id: "grouped", label: "Grouped" }, { id: "ungrouped", label: "Ungrouped" },
] as const;

export function KnowledgeGaps({ heading }: { heading: ReactNode }) {
  const queryClient = useQueryClient();
  const [period, setPeriod] = useState<QuestionPeriod>("30");
  const [view, setView] = useState<QuestionView>("all");
  const [search, setSearch] = useState("");
  const querySearch = useDeferredValue(search.trim());
  const [page, setPage] = useState(0);
  const [threshold, setThreshold] = useState(0.86);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [editor, setEditor] = useState<QuestionGroup | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const answerTrigger = useRef<HTMLElement | null>(null);
  const [drafts, setDrafts] = useState<Record<string, AnswerDraft>>({});
  const [notice, setNotice] = useState("");
  const filters = { period, view, search: querySearch, offset: page * pageSize };
  const dashboard = useQuery({
    queryKey: [...questionKeys.dashboard, filters],
    queryFn: ({ signal }) => listCustomerQuestions(filters, signal),
    retry: false,
  });
  const durable = useQuery({ queryKey: questionKeys.groups, queryFn: listQuestionGroups, enabled: selected.size > 0 });
  const reviews = useQuery({
    queryKey: questionKeys.reviews,
    queryFn: listQuestionReviews,
    refetchInterval: (query) => query.state.data?.some((item) => ["pending_ingestion", "pending_embeddings"].includes(item.status)) ? 5000 : false,
  });
  // The reviews endpoint reconciles completed FAQ ingestion. Refresh open
  // questions when review state changes so resolved gaps disappear promptly.
  const reviewStates = reviews.data?.map((item) => item.id + ":" + item.status).join("|");
  useEffect(() => {
    if (reviewStates !== undefined) {
      void queryClient.invalidateQueries({ queryKey: questionKeys.dashboard });
    }
  }, [reviewStates, queryClient]);

  const operation = useMutation({
    mutationFn: (action: () => Promise<string>) => action(),
    onMutate: () => setNotice(""),
    onSuccess: async (message) => {
      setNotice(message);
      setSelected(new Set());
      setPage(0);
      await Promise.all([questionKeys.dashboard, questionKeys.groups].map((queryKey) => queryClient.invalidateQueries({ queryKey })));
    },
  });

  function openEditor(group: QuestionGroup) {
    answerTrigger.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setEditor(group);
    setEditorOpen(true);
  }

  function resetSelection() {
    setPage(0);
    setSelected(new Set());
  }

  function select(id: string, checked: boolean) {
    setSelected((current) => {
      const next = new Set(current);
      if (checked) next.add(id);
      else next.delete(id);
      return next;
    });
  }

  const groups = dashboard.data?.items ?? [];
  const counts = dashboard.data?.counts;
  const selectedQuestions = groups.flatMap((group) => group.questions).filter((item) => selected.has(item.id));
  const selectedIds = selectedQuestions.map((item) => item.id);
  const draftKey = editor?.questions.map((item) => item.id).sort().join(",") ?? "";
  const readyReviews = reviews.data?.filter((item) => item.status === "ready").length ?? 0;

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        {heading}
        <div className="flex flex-wrap gap-2">
          <DropdownMenu>
            <DropdownMenuTrigger render={<Button variant="outline" className="bg-card" />} aria-label="Date range">
              {periods[period]} <ChevronDown />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-max">
              {(Object.keys(periods) as QuestionPeriod[]).map((value) => (
                <DropdownMenuItem key={value} onClick={() => { setPeriod(value); resetSelection(); }}>{periods[value]}</DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
          <Button disabled={!selectedQuestions.length} title={selectedQuestions.length ? undefined : "Select questions to create an answer"} onClick={() => openEditor({
            id: null, representative: selectedQuestions[0].question, questions: selectedQuestions,
          })}><Plus />Add answer</Button>
        </div>
      </header>

      <QuestionMetrics counts={counts} />

      <section aria-label="Semantic grouping" className="flex flex-wrap items-center gap-x-5 gap-y-3 rounded-xl border bg-card px-4 py-3">
        <h2 className="text-sm font-semibold">Semantic grouping</h2>
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2 sm:min-w-52">
          <label htmlFor="question-similarity" className="text-sm">Similarity</label>
          <span className="hidden text-xs text-muted-foreground sm:inline">Broad</span>
          <input id="question-similarity" type="range" min="0.5" max="1" step="0.01" value={threshold}
            onChange={(event) => setThreshold(event.currentTarget.valueAsNumber)}
            className="min-w-16 flex-1 accent-primary focus-visible:outline-2 focus-visible:outline-ring" />
          <span className="hidden text-xs text-muted-foreground sm:inline">Strict</span>
          <output htmlFor="question-similarity" className="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-semibold text-primary">{threshold.toFixed(2)}</output>
        </div>
        <Button variant="outline" disabled={operation.isPending} onClick={() => operation.mutate(async () => {
          const result = await questionActions.assign(threshold);
          return result.assigned ? `Grouped ${result.assigned} questions and created ${result.created} groups.` : "There are no ungrouped questions to assign.";
        })}><RotateCw />Group questions</Button>
      </section>

      {notice && <p role="status" className="rounded-lg border bg-card px-4 py-2.5 text-sm">{notice}</p>}
      {operation.isError && <p role="alert" className="rounded-lg border border-destructive/30 px-4 py-2.5 text-sm text-destructive">{operation.error.message}</p>}

      <section aria-label="Questions needing review" className="overflow-hidden rounded-xl border bg-card">
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b px-4 pt-2 pb-2">
          <div role="group" aria-label="Question view" className="flex flex-wrap gap-x-3">
            {views.map(({ id, label }) => (
              <button key={id} type="button" aria-pressed={view === id}
                onClick={() => { setView(id); resetSelection(); }}
                className={cn("border-b-2 border-transparent px-1 py-2 text-sm font-semibold text-muted-foreground hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring", view === id && "border-primary text-primary")}>
                {label}{counts && ` ${id === "all" ? counts.open : id === "grouped" ? counts.grouped : counts.open - counts.grouped}`}
              </button>
            ))}
          </div>
          <div className="relative w-full sm:max-w-60">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input type="search" aria-label="Search questions" placeholder="Search questions" maxLength={200} value={search}
              onChange={(event) => { setSearch(event.target.value); resetSelection(); }} className="h-9 pl-9" />
          </div>
        </div>
        {selectedIds.length > 0 && (
          <div className="flex flex-wrap items-center gap-2 border-b bg-primary/8 px-4 py-2.5">
            <span className="mr-1 text-sm font-semibold text-primary">{selectedIds.length} selected</span>
            <DropdownMenu>
              <DropdownMenuTrigger render={<Button size="sm" variant="outline" className="bg-card" />} disabled={operation.isPending || durable.isPending}>
                Move to group <ChevronDown />
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start" className="w-60">
                {durable.data?.map((group) => (
                  <DropdownMenuItem key={group.id} className="break-words" onClick={() => operation.mutate(async () => {
                    const result = await questionActions.move(group.id, selectedIds);
                    return `Moved ${result.moved} questions.`;
                  })}>{group.representative}</DropdownMenuItem>
                ))}
                {!durable.data?.length && <DropdownMenuItem disabled>{durable.isError ? "Could not load groups" : "No saved groups"}</DropdownMenuItem>}
              </DropdownMenuContent>
            </DropdownMenu>
            <Button size="sm" variant="outline" className="bg-card" disabled={operation.isPending || groups.some((group) => group.id && group.questions.some((item) => selected.has(item.id)))}
              onClick={() => operation.mutate(async () => { await questionActions.createGroup(selectedIds); return "New group created."; })}><Plus />New group from selected</Button>
            <Button size="sm" variant="ghost" onClick={() => setSelected(new Set())}>Clear selection</Button>
          </div>
        )}
        {dashboard.isPending ? <p role="status" className="px-4 py-10 text-center text-sm text-muted-foreground">Loading customer questions…</p>
          : dashboard.isError ? (
            <div role="alert" className="space-y-3 px-4 py-10 text-center">
              <p className="text-sm text-destructive">Could not load customer questions.</p>
              <Button variant="outline" size="sm" onClick={() => void dashboard.refetch()}>Try again</Button>
            </div>
          ) : groups.length === 0 ? (
            <div className="grid justify-items-center gap-2 px-4 py-12 text-center">
              <CircleHelp className="mb-1 size-6 text-muted-foreground" />
              <p className="text-sm font-semibold">{search ? "No matching questions" : "No unanswered questions"}</p>
              <p className="text-sm text-muted-foreground">{search ? "Try a different search or date range." : "Questions that need review will appear here."}</p>
            </div>
          ) : (
            <ul className="divide-y divide-border">
              {groups.map((group) => (
                <CustomerQuestionListItem key={group.id ?? group.questions[0].id} group={group} selected={selected} pending={operation.isPending}
                  onSelect={select} onAnswer={openEditor}
                  onReview={(ids, status) => operation.mutate(async () => {
                    await questionActions.review(ids, status);
                    return status === "resolved" ? "Questions resolved." : "Questions dismissed.";
                  })}
                  onDelete={(id) => {
                    if (window.confirm("Delete this group? Its questions will be kept.")) {
                      operation.mutate(async () => { await questionActions.deleteGroup(id); return "Group deleted. Its questions were kept."; });
                    }
                  }} />
              ))}
            </ul>
          )}
        {(page > 0 || dashboard.data?.has_more) && (
          <div className="flex items-center justify-between border-t px-4 py-2">
            <span className="text-xs text-muted-foreground">Page {page + 1}</span>
            <div className="flex gap-1">
              <Button aria-label="Previous page" variant="ghost" size="icon-sm" disabled={page === 0 || dashboard.isFetching} onClick={() => { setSelected(new Set()); setPage(page - 1); }}><ChevronLeft /></Button>
              <Button aria-label="Next page" variant="ghost" size="icon-sm" disabled={!dashboard.data?.has_more || dashboard.isFetching} onClick={() => { setSelected(new Set()); setPage(page + 1); }}><ChevronRight /></Button>
            </div>
          </div>
        )}
      </section>

      {!!reviews.data?.length && (
        <div className="space-y-1 text-xs text-muted-foreground">
          <p>Recent answer submissions · {readyReviews} ready · {reviews.data.length - readyReviews} pending or failed</p>
          {reviews.data.filter((item) => item.status !== "ready").map((item) => (
            <p key={item.id} role={item.status === "failed" ? "alert" : "status"}>
              {item.question}: {item.status === "failed" ? "Processing failed — check knowledge document ingestion and embedding jobs." : item.status.replaceAll("_", " ")}
            </p>
          ))}
        </div>
      )}
      {editor && (
        <CustomerQuestionAnswerDrawer key={draftKey} title={editor.representative} questions={editor.questions} savedDraft={drafts[draftKey]}
          open={editorOpen} finalFocus={answerTrigger}
          onClose={() => setEditorOpen(false)} onCloseComplete={() => setEditor(null)}
          onSave={(draft) => { setDrafts((current) => ({ ...current, [draftKey]: draft })); setNotice("Draft saved for this visit."); setEditorOpen(false); }}
          onPublished={(alreadySubmitted) => {
            setDrafts((current) => {
              const remaining = { ...current };
              delete remaining[draftKey];
              return remaining;
            });
            setNotice(alreadySubmitted ? "This answer was already submitted. Its processing status is shown below." : "Answer submitted. Linked questions will resolve after successful FAQ ingestion and embedding.");
            void queryClient.invalidateQueries({ queryKey: questionKeys.reviews });
            setEditorOpen(false);
          }} />
      )}
    </div>
  );
}

function QuestionMetrics({ counts }: { counts?: DashboardCounts }) {
  const metrics = [
    { label: "Total questions", value: counts?.total },
    { label: "Needs an answer", value: counts?.open },
    { label: "Resolved", value: counts?.resolved },
    { label: "Semantic groups", value: counts?.groups },
  ];
  return (
    <dl className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {metrics.map(({ label, value }) => (
        <div key={label} className={cn("min-w-0 rounded-xl border bg-card p-4", label === "Needs an answer" && "border-amber-500/35 bg-amber-500/6")}>
          <dt className="text-sm font-medium text-muted-foreground">{label}</dt>
          <dd className="mt-1 text-2xl font-semibold tracking-tight tabular-nums">{value?.toLocaleString() ?? "—"}</dd>
          {label === "Resolved" && counts && counts.total > 0 && (
            <progress aria-label="Share of questions resolved" value={counts.resolved} max={counts.total}
              className="block h-1.5 w-full overflow-hidden rounded-full accent-emerald-600" />
          )}
        </div>
      ))}
    </dl>
  );
}
