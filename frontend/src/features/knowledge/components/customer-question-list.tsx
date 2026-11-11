"use client";

import { ChevronDown, Ellipsis, Sparkles } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import type { QuestionGroup } from "../api/knowledge-gap-api";

const dateFormat = new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", year: "numeric" });

export function CustomerQuestionListItem({ group, selected, pending, onSelect, onAnswer, onReview, onDelete }: {
  group: QuestionGroup;
  selected: ReadonlySet<string>;
  pending: boolean;
  onSelect: (id: string, checked: boolean) => void;
  onAnswer: (group: QuestionGroup) => void;
  onReview: (ids: string[], status: "resolved" | "dismissed") => void;
  onDelete: (id: string) => void;
}) {
  const [expanded, setExpanded] = useState(true);
  const groupId = group.id;
  const ids = group.questions.map((item) => item.id);

  return (
    <li className="min-w-0">
      {groupId && (
        <div className="flex min-w-0 flex-wrap items-center gap-2 bg-muted/60 px-4 py-2">
          <button type="button" aria-expanded={expanded} onClick={() => setExpanded(!expanded)}
            className="flex min-w-0 flex-1 items-center gap-2 rounded-sm py-1 text-left text-sm font-semibold focus-visible:outline-2 focus-visible:outline-ring">
            <ChevronDown className={cn("size-4 shrink-0 text-muted-foreground", !expanded && "-rotate-90")} />
            <span className="truncate" title={group.representative}>{group.representative}</span>
          </button>
          <span className="text-xs text-muted-foreground">{ids.length} shown</span>
          <span className="rounded-full bg-amber-500/15 px-2.5 py-1 text-xs font-medium text-amber-800 dark:text-amber-300">Unanswered</span>
          <Button type="button" variant="outline" size="sm" className="bg-card" onClick={() => onAnswer(group)}><Sparkles />Create answer</Button>
          <QuestionMenu label="Group actions" pending={pending}>
            <DropdownMenuItem onClick={() => ids.forEach((id) => onSelect(id, true))}>Select displayed questions</DropdownMenuItem>
            <DropdownMenuItem onClick={() => onReview(ids, "resolved")}>Resolve displayed questions</DropdownMenuItem>
            <DropdownMenuItem onClick={() => onReview(ids, "dismissed")}>Dismiss displayed questions</DropdownMenuItem>
            <DropdownMenuItem variant="destructive" onClick={() => onDelete(groupId)}>Delete group</DropdownMenuItem>
          </QuestionMenu>
        </div>
      )}
      {(!groupId || expanded) && (
        <ul className="divide-y divide-border">
          {group.questions.map((item) => (
            <li key={item.id} className="flex min-w-0 items-center gap-3 px-4 py-2.5 hover:bg-muted/30">
              <Checkbox aria-label={`Select ${item.question}`} checked={selected.has(item.id)} onCheckedChange={(checked) => onSelect(item.id, checked === true)} />
              <button type="button" onClick={() => onAnswer({ representative: item.question, questions: [item], id: null })}
                className="min-w-0 flex-1 rounded-sm text-left text-sm break-words hover:text-primary focus-visible:outline-2 focus-visible:outline-ring">
                {item.question}
              </button>
              <time dateTime={item.created_at} className="hidden shrink-0 text-xs text-muted-foreground sm:block">{dateFormat.format(new Date(item.created_at))}</time>
              <QuestionMenu label={`Actions for ${item.question}`} pending={pending}>
                <DropdownMenuItem onClick={() => onAnswer({ representative: item.question, questions: [item], id: null })}>Create answer</DropdownMenuItem>
                <DropdownMenuItem onClick={() => onReview([item.id], "resolved")}>Resolve question</DropdownMenuItem>
                <DropdownMenuItem onClick={() => onReview([item.id], "dismissed")}>Dismiss question</DropdownMenuItem>
              </QuestionMenu>
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

function QuestionMenu({ label, pending, children }: { label: string; pending: boolean; children: React.ReactNode }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger render={<Button type="button" variant="ghost" size="icon-sm" />} aria-label={label} disabled={pending}>
        <Ellipsis />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-max min-w-44">{children}</DropdownMenuContent>
    </DropdownMenu>
  );
}
