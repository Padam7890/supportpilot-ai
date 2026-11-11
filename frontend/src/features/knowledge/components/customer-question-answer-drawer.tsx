"use client";

import { useState, type RefObject } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import { knowledgeBaseKey, listKnowledgeBases } from "../api/knowledge-base-api";
import { knowledgeKeys } from "../api/knowledge-api";
import { questionActions, questionKeys, type AnswerDraft, type DashboardQuestion } from "../api/knowledge-gap-api";

export function CustomerQuestionAnswerDrawer({ title, questions, savedDraft, open, finalFocus, onClose, onCloseComplete, onSave, onPublished }: {
  title: string;
  questions: DashboardQuestion[];
  savedDraft?: AnswerDraft;
  open: boolean;
  finalFocus: RefObject<HTMLElement | null>;
  onClose: () => void;
  onCloseComplete: () => void;
  onSave: (draft: AnswerDraft) => void;
  onPublished: (alreadySubmitted: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const [question, setQuestion] = useState(savedDraft?.question ?? title);
  const [answer, setAnswer] = useState(savedDraft?.answer ?? "");
  const [selectedBase, setSelectedBase] = useState(savedDraft?.knowledge_base_id);
  const bases = useQuery({ queryKey: knowledgeBaseKey, queryFn: listKnowledgeBases });
  const activeBases = bases.data?.items.filter((base) => base.status === "active") ?? [];
  const base = activeBases.find((item) => item.id === selectedBase)
    ?? activeBases.find((item) => item.is_default) ?? activeBases[0];
  const draft = {
    question: question.trim(), answer: answer.trim(),
    knowledge_base_id: base?.id ?? "", gap_ids: questions.map((item) => item.id),
  };
  const publish = useMutation({
    mutationFn: questionActions.publish,
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: knowledgeKeys.documents });
      void queryClient.invalidateQueries({ queryKey: questionKeys.reviews });
      onPublished(result.already_submitted);
    },
  });

  return (
    <Sheet open={open} onOpenChange={(nextOpen) => { if (!nextOpen && !publish.isPending) onClose(); }}
      onOpenChangeComplete={(nextOpen) => { if (!nextOpen) onCloseComplete(); }}>
      <SheetContent showCloseButton finalFocus={finalFocus} className="inset-y-0 right-0 left-auto top-0 flex h-dvh w-[min(540px,100vw)] max-w-none translate-x-0 translate-y-0 flex-col gap-0 rounded-none border-l border-r-0 bg-background p-0 duration-300 ease-out data-open:slide-in-from-right data-open:zoom-in-100 data-closed:slide-out-to-right data-closed:zoom-out-100 sm:max-w-none">
        <SheetHeader className="shrink-0 px-5 pt-6 pb-4 pr-12 sm:px-7 sm:pr-12">
          <SheetDescription>Create answer</SheetDescription>
          <SheetTitle className="break-words text-xl font-semibold tracking-tight">{title}</SheetTitle>
        </SheetHeader>
        <form className="flex min-h-0 flex-1 flex-col" onSubmit={(event) => { event.preventDefault(); if (base && draft.question && draft.answer && !publish.isPending) publish.mutate(draft); }}>
          <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-5 pb-4 sm:px-7">
            <section aria-label="Covered questions" className="space-y-2">
              <h3 className="text-sm font-semibold">This answer will cover {questions.length} {questions.length === 1 ? "question" : "questions"}</h3>
              <ul className="space-y-2">
                {questions.map((item) => <li key={item.id} className="rounded-lg border bg-card px-3 py-2.5 text-sm break-words">{item.question}</li>)}
              </ul>
            </section>
            <label className="block space-y-2 text-sm font-medium">
              <span>FAQ title</span>
              <Input value={question} maxLength={1000} required onChange={(event) => setQuestion(event.target.value)} />
            </label>
            <label className="block space-y-2 text-sm font-semibold">
              <span>Verified answer</span>
              <Textarea value={answer} maxLength={10000} required onChange={(event) => setAnswer(event.target.value)}
                placeholder="Write the answer your team has verified"
                className="field-sizing-fixed min-h-48 bg-card font-normal sm:min-h-60" />
            </label>
            <div className="space-y-2">
              <p id="answer-knowledge-base" className="text-sm font-medium">Knowledge base</p>
              <Select value={base?.id ?? null} onValueChange={(value) => setSelectedBase(value ?? undefined)} disabled={!activeBases.length}>
                <SelectTrigger aria-labelledby="answer-knowledge-base" className="w-full bg-card"><SelectValue placeholder="Select knowledge base">{base?.name}</SelectValue></SelectTrigger>
                <SelectContent alignItemWithTrigger={false}>
                  {activeBases.map((item) => <SelectItem key={item.id} value={item.id}>{item.name}</SelectItem>)}
                </SelectContent>
              </Select>
              {bases.isError && <p role="alert" className="text-sm text-destructive">Could not load knowledge bases.</p>}
              {bases.isSuccess && !activeBases.length && <p className="text-sm text-muted-foreground">An active knowledge base is required to publish.</p>}
            </div>
            {publish.isError && <p role="alert" className="text-sm text-destructive">{publish.error.message}</p>}
          </div>
          <SheetFooter className="shrink-0 flex-row justify-end gap-2 border-t bg-background px-5 py-4 sm:px-7">
            <Button type="button" variant="outline" disabled={publish.isPending || !question.trim() || !answer.trim()} onClick={() => onSave(draft)}>Save draft</Button>
            <Button type="submit" disabled={publish.isPending || !draft.question || !draft.answer || !base}>
              {publish.isPending ? "Publishing…" : "Publish answer"}
            </Button>
          </SheetFooter>
        </form>
      </SheetContent>
    </Sheet>
  );
}
