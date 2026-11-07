"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient, type UseQueryResult } from "@tanstack/react-query";
import {
  ArrowRight,
  Bell,
  ChevronLeft,
  CircleUser,
  CircleAlert,
  Database,
  Hash,
  MessageSquare,
  Package,
  Search,
  Sparkles,
  Ticket,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { AutomationNodeCanvas } from "./automation-node-canvas";
import { getCurrentUser } from "@/features/auth/api/auth-api";
import { listMembers } from "@/features/organization/api/organization-api";
import { activeTeamsQueryKey, listActiveTeams } from "@/features/organization/api/team-api";
import { aiAgentsKey, listAIAgents } from "@/features/ai/api/ai-agent-api";
import type { WorkflowDraft, DraftStep, Condition, Action } from "../types/workflow-draft";
import { validateWorkflowDraft } from "../utils/validate-workflow-draft";
import { fitCanvasLayout } from "../utils/canvas-layout";
import {
  EMPTY_DRAFT,
  defaultActionForKind,
  defaultConditionForKind,
  issueKeyForStep,
  workflowDraftDefinition,
  workflowDraftFrom,
  workflowDraftPayload,
} from "../utils/workflow-draft-helpers";
import {
  automationKey,
  createAutomation,
  createAutomationFromTemplate,
  listAutomationTemplates,
  listAutomations,
  previewAutomation,
  publishAutomation,
  updateAutomation,
  type AutomationPreview,
} from "../api/automation-api";
import type { User } from "@/features/auth/types/user.types";

const MAX_DRAFT_HISTORY = 50;
const DRAFT_AUTOSAVE_DELAY_MS = 900;
const fieldClass =
  "mt-2 box-border min-h-9 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900 placeholder:text-slate-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/20";

type LibraryCategory = "triggers" | "conditions" | "actions";
type LibraryFilter = "all" | LibraryCategory;

type LibraryItem = {
  id: string;
  category: LibraryCategory;
  group?: "inbox" | "ai" | "messaging" | "shopify";
  name: string;
  description: string;
  icon: LucideIcon;
  available: boolean;
  badge?: string;
  addLabel: string;
  onAdd: () => void;
};

function outcomeStyle(outcome: string) {
  if (outcome === "matched" || outcome === "would_run") return "text-emerald-800";
  if (outcome === "skipped") return "text-amber-900";
  return "text-red-800";
}

export function AutomationWorkspace() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const editParam = searchParams.get("edit");
  const queryClient = useQueryClient();
  const currentUser = useQuery({ queryKey: ["me"], queryFn: getCurrentUser });
  const canManage = currentUser.data?.role === "owner" || currentUser.data?.role === "admin";

  const [draft, setDraft] = useState<WorkflowDraft>(EMPTY_DRAFT);
  const [selectedStep, setSelectedStep] = useState<DraftStep | null>({ type: "trigger" });
  const [showValidation, setShowValidation] = useState(false);
  const [inspectorTab, setInspectorTab] = useState<"configure" | "test">("configure");
  const [libraryFilter, setLibraryFilter] = useState<LibraryFilter>("all");
  const [libraryQuery, setLibraryQuery] = useState("");
  const [draftHistory, setDraftHistory] = useState<{ past: WorkflowDraft[]; future: WorkflowDraft[] }>({
    past: [],
    future: [],
  });
  const [sampleMessage, setSampleMessage] = useState("");
  const [sampleTicketPriority, setSampleTicketPriority] = useState<"" | "low" | "normal" | "high" | "urgent">("");
  const [sampleTicketStatus, setSampleTicketStatus] = useState("");
  const [sampleChannel, setSampleChannel] = useState("");
  const [sampleFirstMessage, setSampleFirstMessage] = useState<boolean | null>(null);
  const [sampleAssigneePresent, setSampleAssigneePresent] = useState<boolean | null>(null);
  const [sampleConversationAiMode, setSampleConversationAiMode] = useState<"" | "ai" | "human">("");
  const [sampleShopifyConnected, setSampleShopifyConnected] = useState<boolean | null>(null);
  const [previewResult, setPreviewResult] = useState<AutomationPreview | null>(null);
  const [editingWorkflow, setEditingWorkflow] = useState<string | null>(null);
  const [autosaveStatus, setAutosaveStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [manualSaveStatus, setManualSaveStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [acknowledgeBroadRule, setAcknowledgeBroadRule] = useState(false);
  /** Errors from save/preview/publish/install (URL-driven messages use separate memos below) */
  const [mutationError, setMutationError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const autosaveQueue = useRef<Promise<void>>(Promise.resolve());
  const autosaveTimer = useRef<number | null>(null);
  const persistedDrafts = useRef(new Map<string, string>());
  const draftRef = useRef(draft);
  const editingWorkflowRef = useRef(editingWorkflow);
  const [persistedDraftSnapshot, setPersistedDraftSnapshot] = useState<string | null>(null);

  useEffect(() => {
    draftRef.current = draft;
    editingWorkflowRef.current = editingWorkflow;
  }, [draft, editingWorkflow]);

  const draftValidation = validateWorkflowDraft(draft);
  const validationIssueKeys = useMemo(() => {
    const keys = new Set<string>();
    for (const issue of draftValidation.issues) {
      keys.add(issueKeyForStep(issue.step));
    }
    return keys;
  }, [draftValidation.issues]);

  const members = useQuery({ queryKey: ["users"], queryFn: listMembers, enabled: canManage });
  const teams = useQuery({ queryKey: activeTeamsQueryKey, queryFn: listActiveTeams, enabled: canManage });
  const aiAgents = useQuery({ queryKey: aiAgentsKey, queryFn: listAIAgents, enabled: canManage });

  const memberNamesById = useMemo(() => {
    const map = new Map<string, string>();
    for (const m of members.data ?? []) {
      map.set(m.id, m.full_name);
    }
    return map;
  }, [members.data]);

  const aiAgentNamesById = useMemo(() => {
    const map = new Map<string, string>();
    for (const agent of aiAgents.data?.items ?? []) {
      map.set(agent.id, agent.name);
    }
    return map;
  }, [aiAgents.data]);

  const hasUnsavedEdits =
    editingWorkflow !== null && persistedDraftSnapshot !== JSON.stringify(workflowDraftPayload(draft));

  const loadedWorkflowParamRef = useRef<string | null>(null);
  const templateInstallAttemptedRef = useRef<string | null>(null);
  const workflowsList = useQuery({ queryKey: automationKey, queryFn: listAutomations });
  const templatesList = useQuery({ queryKey: [...automationKey, "templates"], queryFn: () => listAutomationTemplates() });

  const templateParam = searchParams.get("template");
  const templateCapabilityError = useMemo(() => {
    if (!templateParam || !templatesList.data) return null;
    const tpl = templatesList.data.find((t) => t.id === templateParam);
    if (!tpl || tpl.available) return null;
    return `Template requires: ${tpl.missing_capabilities.length ? tpl.missing_capabilities.join(", ") : "integrations"}`;
  }, [templateParam, templatesList.data]);

  const workflowNotFoundError = useMemo(() => {
    if (!editParam || editParam === "new" || !workflowsList.data) return null;
    const wf = workflowsList.data.find((w) => w.id === editParam);
    if (wf) return null;
    return "That workflow was not found. It may have been removed.";
  }, [editParam, workflowsList.data]);

  const bannerError = templateCapabilityError ?? workflowNotFoundError ?? mutationError;

  const activeWorkflow = useMemo(() => {
    if (!editingWorkflow || !workflowsList.data) return null;
    return workflowsList.data.find((w) => w.id === editingWorkflow) ?? null;
  }, [editingWorkflow, workflowsList.data]);

  const installTemplate = useMutation({
    mutationFn: (templateId: string) => createAutomationFromTemplate({ template_id: templateId }),
    onSuccess: async (created) => {
      setMutationError(null);
      setSuccessMessage("Workflow created from template.");
      setEditingWorkflow(created.id);
      const next = workflowDraftFrom(created);
      draftRef.current = next;
      setDraft(next);
      const snap = JSON.stringify(workflowDraftPayload(next));
      persistedDrafts.current.set(created.id, snap);
      setPersistedDraftSnapshot(snap);
      await queryClient.invalidateQueries({ queryKey: automationKey });
      router.replace(`/dashboard/automations?edit=${encodeURIComponent(created.id)}`);
    },
    onError: (error: Error) => setMutationError(error.message),
  });
  const installTemplateMutateRef = useRef(installTemplate.mutate);
  useEffect(() => {
    installTemplateMutateRef.current = installTemplate.mutate;
  }, [installTemplate.mutate]);

  /** Open workflow from ?edit= or ?template= when list loads */
  useEffect(() => {
    /* Sync URL → editor once workflow/template queries resolve. TanStack’s useMutation return is not
     * referentially stable; use a ref for mutate to avoid effect loops and exhaustive-deps noise. */
    /* eslint-disable react-hooks/set-state-in-effect */
    if (templateParam && templatesList.data) {
      const tpl = templatesList.data.find((t) => t.id === templateParam);
      if (tpl && !tpl.available) {
        return;
      }
      if (tpl?.available && templateInstallAttemptedRef.current !== templateParam) {
        templateInstallAttemptedRef.current = templateParam;
        installTemplateMutateRef.current(templateParam);
        router.replace("/dashboard/automations?edit=new");
      }
      return;
    }
    if (!editParam || !workflowsList.data) return;
    if (editParam === "new") {
      // `useMutation()` returns a new object every render; including it in deps caused this effect
      // to re-run forever while on ?edit=new. Only reset when navigating *to* a new blank workflow.
      if (loadedWorkflowParamRef.current === "new") return;
      loadedWorkflowParamRef.current = "new";
      // This effect synchronizes the editor with browser navigation after the workflow query resolves.
      setEditingWorkflow(null);
      draftRef.current = EMPTY_DRAFT;
      setDraft(EMPTY_DRAFT);
      setSelectedStep({ type: "trigger" });
      setPersistedDraftSnapshot(null);
      setAutosaveStatus("idle");
      setDraftHistory({ past: [], future: [] });
      return;
    }
    if (loadedWorkflowParamRef.current === editParam) return;
    const wf = workflowsList.data.find((w) => w.id === editParam);
    if (!wf) {
      return;
    }
    loadedWorkflowParamRef.current = editParam;
    setMutationError(null);
    setEditingWorkflow(wf.id);
    const next = workflowDraftFrom(wf);
    draftRef.current = next;
    setDraft(next);
    const snap = JSON.stringify(workflowDraftPayload(next));
    persistedDrafts.current.set(wf.id, snap);
    setPersistedDraftSnapshot(snap);
    setSelectedStep({ type: "trigger" });
    setAutosaveStatus("idle");
    setDraftHistory({ past: [], future: [] });
    setShowValidation(false);
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [editParam, workflowsList.data, templateParam, templatesList.data, router]);

  const create = useMutation({
    mutationFn: (values: Parameters<typeof createAutomation>[0]) => createAutomation(values),
    onSuccess: async (created) => {
      setMutationError(null);
      setSuccessMessage("Draft saved.");
      setEditingWorkflow(created.id);
      const next = workflowDraftFrom(created);
      draftRef.current = next;
      setDraft(next);
      const snap = JSON.stringify(workflowDraftPayload(next));
      persistedDrafts.current.set(created.id, snap);
      setPersistedDraftSnapshot(snap);
      await queryClient.invalidateQueries({ queryKey: automationKey });
      router.replace(`/dashboard/automations?edit=${encodeURIComponent(created.id)}`);
    },
    onError: (error: Error) => {
      setSuccessMessage(null);
      setMutationError(error.message);
    },
  });

  const saveDraft = useMutation({
    mutationFn: async () => {
      if (!editingWorkflow) throw new Error("Nothing to save.");
      await autosaveQueue.current.catch(() => undefined);
      const payload = workflowDraftPayload(draftRef.current);
      return updateAutomation(editingWorkflow, payload);
    },
    onSuccess: async (updated) => {
      setMutationError(null);
      setSuccessMessage("Draft saved.");
      const next = workflowDraftFrom(updated);
      draftRef.current = next;
      setDraft(next);
      const snap = JSON.stringify(workflowDraftPayload(next));
      persistedDrafts.current.set(updated.id, snap);
      setPersistedDraftSnapshot(snap);
      await queryClient.invalidateQueries({ queryKey: automationKey });
      setManualSaveStatus("saved");
      window.setTimeout(() => setManualSaveStatus("idle"), 2000);
    },
    onError: (error: Error) => {
      setManualSaveStatus("error");
      setMutationError(error.message);
    },
    onMutate: () => setManualSaveStatus("saving"),
  });

  const publish = useMutation({
    mutationFn: async () => {
      const id = editingWorkflowRef.current;
      if (!id) throw new Error("Save the workflow first.");
      if (autosaveTimer.current !== null) {
        window.clearTimeout(autosaveTimer.current);
        autosaveTimer.current = null;
      }
      await autosaveQueue.current.catch(() => undefined);
      const payload = workflowDraftPayload(draftRef.current);
      const snap = JSON.stringify(payload);
      if (persistedDrafts.current.get(id) !== snap) {
        await updateAutomation(id, payload);
        persistedDrafts.current.set(id, snap);
        setPersistedDraftSnapshot(snap);
      }
      await publishAutomation(id);
    },
    onSuccess: async () => {
      setMutationError(null);
      setSuccessMessage("Version published.");
      setAcknowledgeBroadRule(false);
      await queryClient.invalidateQueries({ queryKey: automationKey });
    },
    onError: (error: Error) => setMutationError(error.message),
  });

  const preview = useMutation({
    mutationFn: previewAutomation,
    onSuccess: (result) => {
      setMutationError(null);
      setPreviewResult(result);
      setInspectorTab("test");
    },
    onError: (error: Error) => {
      setPreviewResult(null);
      setMutationError(error.message);
    },
  });

  useEffect(() => {
    if (!editingWorkflow || draftValidation.errors.length > 0) return;
    const workflowId = editingWorkflow;
    const values = workflowDraftPayload(draft);
    const snapshot = JSON.stringify(values);
    if (persistedDrafts.current.get(workflowId) === snapshot) return;

    autosaveTimer.current = window.setTimeout(() => {
      autosaveTimer.current = null;
      setAutosaveStatus("saving");
      const nextSave = autosaveQueue.current.catch(() => undefined).then(async () => {
        if (editingWorkflowRef.current !== workflowId || persistedDrafts.current.get(workflowId) === snapshot) return;
        await updateAutomation(workflowId, values);
        persistedDrafts.current.set(workflowId, snapshot);
        setPersistedDraftSnapshot(snapshot);
        if (
          editingWorkflowRef.current === workflowId &&
          JSON.stringify(workflowDraftPayload(draftRef.current)) === snapshot
        ) {
          setAutosaveStatus("saved");
        }
        await queryClient.invalidateQueries({ queryKey: automationKey });
      });
      autosaveQueue.current = nextSave.catch(() => {
        if (
          editingWorkflowRef.current === workflowId &&
          JSON.stringify(workflowDraftPayload(draftRef.current)) === snapshot
        ) {
          setAutosaveStatus("error");
          setMutationError(
            "Draft autosave failed. Your edits are still on this screen; use Save draft or change a field to retry.",
          );
        }
      });
    }, DRAFT_AUTOSAVE_DELAY_MS);

    return () => {
      if (autosaveTimer.current !== null) {
        window.clearTimeout(autosaveTimer.current);
        autosaveTimer.current = null;
      }
    };
  }, [draft, draftValidation.errors.length, editingWorkflow, queryClient]);

  const updateDraft = useCallback(
    (update: Partial<WorkflowDraft> | ((current: WorkflowDraft) => WorkflowDraft)) => {
      const current = draftRef.current;
      const next = typeof update === "function" ? update(current) : { ...current, ...update };
      if (next === current) return;
      const condLen = next.conditions.length;
      const actLen = next.actions.length;
      const normalized: WorkflowDraft =
        condLen === current.conditions.length && actLen === current.actions.length
          ? next
          : { ...next, canvasLayout: fitCanvasLayout(next.canvasLayout, condLen, actLen) };

      setDraftHistory((history) => ({
        past: [...history.past.slice(-(MAX_DRAFT_HISTORY - 1)), current],
        future: [],
      }));
      setAutosaveStatus("idle");
      setPreviewResult(null);
      draftRef.current = normalized;
      setDraft(normalized);
    },
    [],
  );

  const undoDraft = useCallback(() => {
    setDraftHistory((history) => {
      const previous = history.past.at(-1);
      if (!previous) return history;
      const current = draftRef.current;
      draftRef.current = previous;
      setDraft(previous);
      setAutosaveStatus("idle");
      setPreviewResult(null);
      return {
        past: history.past.slice(0, -1),
        future: [...history.future, current].slice(-MAX_DRAFT_HISTORY),
      };
    });
  }, []);

  const redoDraft = useCallback(() => {
    setDraftHistory((history) => {
      const next = history.future.at(-1);
      if (!next) return history;
      const current = draftRef.current;
      draftRef.current = next;
      setDraft(next);
      setAutosaveStatus("idle");
      setPreviewResult(null);
      return {
        past: [...history.past, current].slice(-MAX_DRAFT_HISTORY),
        future: history.future.slice(0, -1),
      };
    });
  }, []);

  const addConditionAt = useCallback((atIndex: number, kind: Condition["kind"] = "contains_keyword") => {
    updateDraft((current) => {
      const nextConditions = [...current.conditions];
      nextConditions.splice(atIndex, 0, defaultConditionForKind(kind));
      return {
        ...current,
        conditions: nextConditions,
        canvasLayout: fitCanvasLayout(current.canvasLayout, nextConditions.length, current.actions.length),
      };
    });
    setSelectedStep({ type: "condition", index: atIndex });
  }, [updateDraft]);

  const addActionAt = useCallback((atIndex: number, kind: Action["kind"] = "set_priority") => {
    updateDraft((current) => {
      const nextActions = [...current.actions];
      nextActions.splice(atIndex, 0, defaultActionForKind(kind));
      return {
        ...current,
        actions: nextActions,
        canvasLayout: fitCanvasLayout(current.canvasLayout, current.conditions.length, nextActions.length),
      };
    });
    setSelectedStep({ type: "action", index: atIndex });
  }, [updateDraft]);

  function removeCondition(index: number) {
    updateDraft((current) => {
      const next = current.conditions.filter((_, i) => i !== index);
      return {
        ...current,
        conditions: next,
        canvasLayout: fitCanvasLayout(current.canvasLayout, next.length, current.actions.length),
      };
    });
    setSelectedStep((s) => {
      if (!s) return { type: "trigger" };
      if (s.type === "condition" && s.index === index) return { type: "trigger" };
      if (s.type === "condition" && s.index > index) return { type: "condition", index: s.index - 1 };
      return s;
    });
  }

  function removeAction(index: number) {
    updateDraft((current) => {
      if (current.actions.length <= 1) return current;
      const next = current.actions.filter((_, i) => i !== index);
      return {
        ...current,
        actions: next,
        canvasLayout: fitCanvasLayout(current.canvasLayout, current.conditions.length, next.length),
      };
    });
    setSelectedStep((s) => {
      if (!s) return { type: "trigger" };
      if (s.type === "action" && s.index === index) return { type: "trigger" };
      if (s.type === "action" && s.index > index) return { type: "action", index: s.index - 1 };
      return s;
    });
  }

  function moveCondition(index: number, delta: -1 | 1) {
    updateDraft((current) => {
      const j = index + delta;
      if (j < 0 || j >= current.conditions.length) return current;
      const next = [...current.conditions];
      [next[index], next[j]] = [next[j]!, next[index]!];
      const layoutNext = { ...current.canvasLayout, conditions: [...(current.canvasLayout.conditions ?? [])] };
      const pi = layoutNext.conditions[index];
      const pj = layoutNext.conditions[j];
      if (pi && pj) {
        layoutNext.conditions[index] = pj;
        layoutNext.conditions[j] = pi;
      }
      return { ...current, conditions: next, canvasLayout: layoutNext };
    });
    setSelectedStep((s) => {
      if (s?.type !== "condition") return s;
      if (s.index === index) return { type: "condition", index: index + delta };
      if (s.index === index + delta) return { type: "condition", index: index };
      return s;
    });
  }

  function moveAction(index: number, delta: -1 | 1) {
    updateDraft((current) => {
      const j = index + delta;
      if (j < 0 || j >= current.actions.length) return current;
      const next = [...current.actions];
      [next[index], next[j]] = [next[j]!, next[index]!];
      const layoutNext = { ...current.canvasLayout, actions: [...(current.canvasLayout.actions ?? [])] };
      const pi = layoutNext.actions[index];
      const pj = layoutNext.actions[j];
      if (pi && pj) {
        layoutNext.actions[index] = pj;
        layoutNext.actions[j] = pi;
      }
      return { ...current, actions: next, canvasLayout: layoutNext };
    });
    setSelectedStep((s) => {
      if (s?.type !== "action") return s;
      if (s.index === index) return { type: "action", index: index + delta };
      if (s.index === index + delta) return { type: "action", index: index };
      return s;
    });
  }

  const liveVersion = activeWorkflow?.published_version ?? null;
  const draftVersion = activeWorkflow?.draft_version ?? null;
  const lastPublishedLabel = activeWorkflow?.published_version ? `Live v${activeWorkflow.published_version}` : "Not published";

  const editingStatus =
    draftVersion != null ? `Editing draft v${draftVersion}` : "Editing draft";
  const liveStatusLine = `${lastPublishedLabel}${liveVersion != null && draftVersion != null && liveVersion !== draftVersion ? ` · draft v${draftVersion}` : ""}`;

  const persistStatusLine = (() => {
    if (!editingWorkflow) return "New workflow — save to enable autosave.";
    if (draftValidation.errors.length > 0) return "Fix validation to enable autosave.";
    if (manualSaveStatus === "saving" || saveDraft.isPending) return "Saving…";
    if (manualSaveStatus === "error") return "Save failed.";
    if (manualSaveStatus === "saved") return "Saved.";
    if (autosaveStatus === "saving") return "Saving…";
    if (autosaveStatus === "error") return "Save failed.";
    if (autosaveStatus === "saved") return "Saved.";
    if (hasUnsavedEdits) return "Unsaved changes";
    return "Saved.";
  })();

  const broadPublishBlock =
    draft.conditions.length === 0 &&
    (draft.actions.some((a) => a.kind === "assign_to_user") ||
      draft.actions.some((a) => a.kind === "set_priority"));
  const canPublish =
    canManage &&
    editingWorkflow &&
    draftValidation.errors.length === 0 &&
    (!broadPublishBlock || acknowledgeBroadRule);

  function scrollToStep(step: DraftStep) {
    setSelectedStep(step);
    setInspectorTab("configure");
    requestAnimationFrame(() => {
      const el = document.querySelector(`[data-automation-step="${issueKeyForStep(step)}"]`);
      el?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  }

  function handleSaveDraftClick() {
    setShowValidation(true);
    if (draftValidation.errors.length > 0) return;
    setMutationError(null);
    if (!editingWorkflow) {
      create.mutate(workflowDraftPayload(draft));
      return;
    }
    saveDraft.mutate();
  }

  function handleTestWorkflow() {
    setShowValidation(true);
    if (draftValidation.errors.length > 0 || !sampleMessage.trim()) return;
    preview.mutate({
      definition: workflowDraftDefinition(draft),
      sample_message: sampleMessage.trim(),
      sample_ticket_priority: sampleTicketPriority || null,
      sample_ticket_status: sampleTicketStatus.trim() || null,
      sample_channel: sampleChannel.trim() || null,
      sample_is_first_customer_message: sampleFirstMessage,
      sample_assignee_present: sampleAssigneePresent,
      sample_conversation_ai_mode: sampleConversationAiMode || null,
      sample_shopify_connected: sampleShopifyConnected,
    });
  }

  function handlePublish() {
    setShowValidation(true);
    if (draftValidation.errors.length > 0 || !canPublish) return;
    publish.mutate();
  }

  const filteredLibrary = useMemo((): LibraryItem[] => {
    /* eslint-disable react-hooks/refs -- catalog rows carry click handlers that close over draft updaters; they are not invoked during this render */
    const conditionInsert = draft.conditions.length;
    const actionInsert = draft.actions.length;
    const libraryRows: LibraryItem[] = [
      {
        id: "trigger-message",
        category: "triggers",
        group: "inbox",
        name: "Incoming customer message",
        description: "When a customer sends a message on a connected channel.",
        icon: MessageSquare,
        available: true,
        addLabel: "Use trigger",
        onAdd: () => {
          setSelectedStep({ type: "trigger" });
          setInspectorTab("configure");
        },
      },
      {
        id: "cond-keyword",
        category: "conditions",
        group: "inbox",
        name: "Message text",
        description: "Match phrases in the customer message.",
        icon: Hash,
        available: true,
        addLabel: "Add",
        onAdd: () => addConditionAt(conditionInsert, "contains_keyword"),
      },
      {
        id: "cond-channel",
        category: "conditions",
        group: "inbox",
        name: "Channel",
        description: "Filter by channel name or account.",
        icon: MessageSquare,
        available: true,
        addLabel: "Add",
        onAdd: () => addConditionAt(conditionInsert, "channel_is"),
      },
      {
        id: "cond-priority",
        category: "conditions",
        group: "inbox",
        name: "Ticket priority",
        description: "Compare the ticket priority.",
        icon: Ticket,
        available: true,
        addLabel: "Add",
        onAdd: () => addConditionAt(conditionInsert, "ticket_priority_is"),
      },
      {
        id: "cond-status",
        category: "conditions",
        group: "inbox",
        name: "Ticket status",
        description: "Compare ticket status text.",
        icon: Ticket,
        available: true,
        addLabel: "Add",
        onAdd: () => addConditionAt(conditionInsert, "ticket_status_is"),
      },
      {
        id: "cond-ai-mode",
        category: "conditions",
        group: "ai",
        name: "AI mode",
        description: "Match whether AI or human mode is active.",
        icon: Sparkles,
        available: true,
        addLabel: "Add",
        onAdd: () => addConditionAt(conditionInsert, "conversation_ai_mode_is"),
      },
      {
        id: "cond-assignee",
        category: "conditions",
        group: "inbox",
        name: "Assignee presence",
        description: "Check if the ticket already has an assignee.",
        icon: CircleUser,
        available: true,
        addLabel: "Add",
        onAdd: () => addConditionAt(conditionInsert, "assignee_present"),
      },
      {
        id: "cond-shopify",
        category: "conditions",
        group: "shopify",
        name: "Shopify connected",
        description: "Requires a connected Shopify store.",
        icon: Package,
        available: true,
        addLabel: "Add",
        onAdd: () => addConditionAt(conditionInsert, "shopify_store_connected"),
      },
      {
        id: "act-priority",
        category: "actions",
        group: "inbox",
        name: "Set priority",
        description: "Update ticket priority.",
        icon: Ticket,
        available: true,
        addLabel: "Add",
        onAdd: () => addActionAt(actionInsert, "set_priority"),
      },
      {
        id: "act-assign",
        category: "actions",
        group: "inbox",
        name: "Assign teammate",
        description: "Assign the ticket to a person.",
        icon: ArrowRight,
        available: true,
        addLabel: "Add",
        onAdd: () => {
          const nextIndex = actionInsert;
          updateDraft((c) => {
            const next = [...c.actions, { kind: "assign_to_user" as const, user_id: "", only_if_unassigned: false }];
            return {
              ...c,
              actions: next,
              canvasLayout: fitCanvasLayout(c.canvasLayout, c.conditions.length, next.length),
            };
          });
          setSelectedStep({ type: "action", index: nextIndex });
        },
      },
      {
        id: "act-assign-team",
        category: "actions",
        group: "inbox",
        name: "Assign to support team",
        description: "Route the ticket to a tenant support team.",
        icon: ArrowRight,
        available: true,
        addLabel: "Add",
        onAdd: () => addActionAt(actionInsert, "assign_to_team"),
      },
      {
        id: "act-status",
        category: "actions",
        group: "inbox",
        name: "Set ticket status",
        description: "Update open / pending / resolved / closed.",
        icon: Ticket,
        available: true,
        addLabel: "Add",
        onAdd: () => addActionAt(actionInsert, "set_ticket_status"),
      },
      {
        id: "act-ai-mode",
        category: "actions",
        group: "ai",
        name: "Set AI mode",
        description: "Switch conversation between AI and human.",
        icon: Sparkles,
        available: true,
        addLabel: "Add",
        onAdd: () => addActionAt(actionInsert, "set_conversation_ai_mode"),
      },
      {
        id: "act-route-ai-bot",
        category: "actions",
        group: "ai",
        name: "Route to AI bot",
        description: "Choose the active bot for future widget replies in this conversation.",
        icon: Sparkles,
        available: true,
        addLabel: "Add",
        onAdd: () => addActionAt(actionInsert, "route_to_ai_bot"),
      },
      {
        id: "act-widget-bot-routing",
        category: "actions",
        group: "ai",
        name: "Restore widget bot routing",
        description: "Clear a pinned bot and resume the widget’s configured multi-bot routing.",
        icon: Sparkles,
        available: true,
        addLabel: "Add",
        onAdd: () => addActionAt(actionInsert, "restore_widget_bot_routing"),
      },
      {
        id: "act-internal-note",
        category: "actions",
        group: "inbox",
        name: "Internal note",
        description: "Add a private note to the conversation thread.",
        icon: MessageSquare,
        available: true,
        addLabel: "Add",
        onAdd: () => addActionAt(actionInsert, "add_internal_note"),
      },
      {
        id: "act-human-approval",
        category: "actions",
        group: "inbox",
        name: "Require human approval",
        description: "Pause this run until an Owner/Admin approves or rejects it.",
        icon: CircleAlert,
        available: true,
        addLabel: "Add",
        onAdd: () => addActionAt(actionInsert, "require_human_approval"),
      },
      {
        id: "act-commerce-approval",
        category: "actions",
        group: "shopify",
        name: "Request cancellation review",
        description: "Verify the customer's Shopify order and send a cancellation request to human review.",
        icon: Package,
        available: true,
        addLabel: "Add",
        onAdd: () => addActionAt(actionInsert, "request_commerce_approval"),
      },
      {
        id: "ai-classify",
        category: "actions",
        group: "ai",
        name: "Classify intent (AI)",
        description: "Route using an AI classifier.",
        icon: Sparkles,
        available: false,
        badge: "Coming soon",
        addLabel: "Coming soon",
        onAdd: () => undefined,
      },
      {
        id: "msg-notify",
        category: "actions",
        group: "messaging",
        name: "Notify teammate",
        description: "Send an internal notification.",
        icon: Bell,
        available: false,
        badge: "Coming soon",
        addLabel: "Coming soon",
        onAdd: () => undefined,
      },
      {
        id: "shop-lookup",
        category: "actions",
        group: "shopify",
        name: "Look up Shopify order",
        description: "Verified read-only lookup (internal note).",
        icon: Package,
        available: true,
        addLabel: "Add",
        onAdd: () => addActionAt(actionInsert, "lookup_shopify_order"),
      },
      {
        id: "shop-catalog",
        category: "actions",
        group: "shopify",
        name: "Search Shopify catalog",
        description: "Read-only product titles for recommendations.",
        icon: Search,
        available: true,
        addLabel: "Add",
        onAdd: () => addActionAt(actionInsert, "search_shopify_catalog"),
      },
      {
        id: "shopify-kb",
        category: "actions",
        group: "shopify",
        name: "Draft AI reply",
        description: "Ground replies on linked knowledge.",
        icon: Database,
        available: false,
        badge: "Coming soon",
        addLabel: "Coming soon",
        onAdd: () => undefined,
      },
    ];

    const q = libraryQuery.trim().toLowerCase();
    const out: LibraryItem[] = [];
    for (let i = 0; i < libraryRows.length; i += 1) {
      const row = libraryRows[i]!;
      if (libraryFilter !== "all" && row.category !== libraryFilter) continue;
      if (
        q &&
        !row.name.toLowerCase().includes(q) &&
        !row.description.toLowerCase().includes(q) &&
        !(row.badge?.toLowerCase().includes(q) ?? false)
      ) {
        continue;
      }
      out.push(row);
    }
    return out;
    /* eslint-enable react-hooks/refs */
  }, [
    draft.conditions.length,
    draft.actions.length,
    libraryFilter,
    libraryQuery,
    addConditionAt,
    addActionAt,
    updateDraft,
  ]);

  function onLibraryRowKeyDown(event: KeyboardEvent<HTMLDivElement>, item: LibraryItem) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      if (item.available) item.onAdd();
    }
  }

  const publishErrorSummary =
    showValidation && draftValidation.errors.length > 0 ? (
      <div className="max-w-md text-left">
        <p className="text-[11px] font-semibold text-red-800">Fix before publishing:</p>
        <ul className="mt-1 max-h-24 list-disc overflow-y-auto pl-4 text-[11px] text-red-800">
          {draftValidation.issues.slice(0, 5).map((issue, i) => (
            <li key={i}>
              <button
                type="button"
                className="text-left underline decoration-red-700/70 hover:text-red-950"
                onClick={() => scrollToStep(issue.step)}
              >
                {issue.message}
              </button>
            </li>
          ))}
        </ul>
      </div>
    ) : null;

  const runsOnEveryLine =
    draft.conditions.length === 0
      ? "Runs on every customer message for this trigger (no condition group)."
      : null;

  if (!canManage) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4 bg-slate-50 p-8 text-center text-slate-900">
        <p className="text-sm text-slate-600">You need owner or admin access to edit automations.</p>
        <Link href="/dashboard/automations" className="text-sm font-medium text-teal-700 underline underline-offset-2 hover:text-teal-800">
          Back to workflows
        </Link>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col bg-slate-50 text-slate-900">
      <header className="z-10 shrink-0 border-b border-slate-200 bg-white px-4 py-3 sm:px-5">
        <div className="flex min-w-0 flex-col gap-3">
          <div className="flex min-w-0 flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <Link
              href="/dashboard/automations"
              className="inline-flex min-h-9 shrink-0 items-center gap-1 self-start text-sm font-medium text-slate-600 hover:text-slate-900"
            >
              <ChevronLeft size={16} aria-hidden />
              Automations
            </Link>
            <div className="flex shrink-0 flex-wrap items-center gap-2 sm:justify-end">
              <Button
                type="button"
                size="sm"
                variant="secondary"
                aria-label={create.isPending || saveDraft.isPending ? "Saving workflow" : "Save workflow draft"}
                disabled={create.isPending || saveDraft.isPending || (!editingWorkflow && draftValidation.errors.length > 0)}
                onClick={handleSaveDraftClick}
              >
                {create.isPending || saveDraft.isPending ? "Saving…" : "Save draft"}
              </Button>
              <Button
                type="button"
                size="sm"
                variant="secondary"
                aria-label="Run test with sample data from header"
                disabled={preview.isPending || draftValidation.errors.length > 0 || !sampleMessage.trim()}
                onClick={handleTestWorkflow}
              >
                {preview.isPending ? "Testing…" : "Test workflow"}
              </Button>
              <div className="flex min-w-[7rem] flex-col gap-1">
                <Button
                  type="button"
                  size="sm"
                  variant="primary"
                  className="bg-teal-700 hover:bg-teal-800 focus-visible:ring-teal-500/30"
                  disabled={!canPublish || publish.isPending || !editingWorkflow}
                  onClick={handlePublish}
                >
                  {publish.isPending ? "…" : "Publish"}
                </Button>
                {publishErrorSummary}
              </div>
            </div>
          </div>
          <div className="min-w-0">
            <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-slate-500" htmlFor="workflow-name-input">
              Workflow name
            </label>
            <input
              id="workflow-name-input"
              required
              minLength={2}
              maxLength={120}
              value={draft.name}
              onChange={(e) => updateDraft({ name: e.target.value })}
              className="min-h-10 w-full max-w-3xl rounded-lg border border-slate-200 bg-white px-3 py-2 text-base font-semibold text-slate-900 placeholder:text-slate-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500/20"
              placeholder="Untitled workflow"
            />
          </div>
          <div className="min-w-0 border-t border-slate-100 pt-2">
            <p
              className="flex flex-wrap items-baseline gap-x-1.5 gap-y-0.5 text-[11px] leading-relaxed text-slate-500"
              title={`${editingWorkflow ? editingStatus : "New draft"} · ${liveStatusLine} · ${persistStatusLine}`}
            >
              <span className="min-w-0 shrink">{editingWorkflow ? editingStatus : "New draft"}</span>
              <span className="text-slate-300" aria-hidden>
                ·
              </span>
              <span className="min-w-0 shrink">{liveStatusLine}</span>
              <span className="text-slate-300" aria-hidden>
                ·
              </span>
              <span className="min-w-0 shrink">{persistStatusLine}</span>
            </p>
            {runsOnEveryLine && (
              <label className="mt-2 flex cursor-pointer items-start gap-2 text-[11px] text-amber-900">
                <input
                  type="checkbox"
                  checked={acknowledgeBroadRule}
                  onChange={(e) => setAcknowledgeBroadRule(e.target.checked)}
                  className="mt-0.5 rounded border-amber-300"
                />
                <span className="leading-snug">Broad rule: no conditions. Confirm before publishing.</span>
              </label>
            )}
          </div>
        </div>
      </header>

      <div className="flex min-h-0 flex-1 flex-col overflow-y-auto px-4 pb-3 pt-3 sm:px-5 lg:overflow-hidden">
        {(bannerError || successMessage) && (
          <div className="mb-3 flex flex-wrap gap-2">
            {bannerError && (
              <p
                role="alert"
                className="flex items-start gap-2 rounded-lg border border-red-100 bg-red-50 px-3 py-2 text-xs text-red-800"
              >
                <CircleAlert size={16} className="mt-0.5 shrink-0" />
                {bannerError}
              </p>
            )}
            {successMessage && (
              <p role="status" className="rounded-lg border border-emerald-100 bg-emerald-50 px-3 py-2 text-xs text-emerald-800">
                {successMessage}
              </p>
            )}
          </div>
        )}

        <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 lg:min-h-0 lg:grid-cols-[minmax(0,200px)_minmax(0,1fr)_minmax(0,260px)] lg:grid-rows-1 lg:items-stretch lg:gap-3 lg:overflow-hidden xl:grid-cols-[minmax(0,220px)_minmax(0,1fr)_minmax(0,280px)] [&>*]:min-h-0">
          <aside
            className="flex max-h-80 min-h-0 flex-col overflow-hidden rounded-md border border-slate-200/90 bg-white lg:max-h-none"
            aria-label="Node library"
          >
            <div className="border-b border-slate-100 p-2.5">
              <div className="relative">
                <Search size={14} className="pointer-events-none absolute left-2 top-2 text-slate-400" />
                <input
                  type="search"
                  value={libraryQuery}
                  onChange={(e) => setLibraryQuery(e.target.value)}
                  placeholder="Search steps"
                  className="box-border w-full rounded-md border border-slate-200 py-1.5 pl-7 pr-2 text-sm text-slate-900 placeholder:text-slate-400"
                  aria-label="Search nodes"
                />
              </div>
              <div className="mt-2 flex flex-wrap gap-1">
                {(
                  [
                    ["all", "All"],
                    ["triggers", "Triggers"],
                    ["conditions", "Conditions"],
                    ["actions", "Actions"],
                  ] as const
                ).map(([id, label]) => (
                  <button
                    key={id}
                    type="button"
                    onClick={() => setLibraryFilter(id)}
                    className={`rounded px-1.5 py-0.5 text-[11px] font-medium ${
                      libraryFilter === id ? "bg-slate-800 text-white" : "text-slate-600 hover:bg-slate-100"
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
            <ul className="min-h-0 flex-1 overflow-y-auto p-1.5 text-sm">
              {(["inbox", "ai", "messaging", "shopify"] as const).map((group) => {
                const inGroup = filteredLibrary.filter((i) => i.group === group);
                if (inGroup.length === 0) return null;
                return (
                  <li key={group} className="mb-2">
                    <p className="mb-1 px-1 text-[10px] font-medium uppercase tracking-wide text-slate-400">
                      {group === "inbox"
                        ? "Inbox"
                        : group === "ai"
                          ? "AI"
                          : group === "messaging"
                            ? "Messaging"
                            : "Shopify"}
                    </p>
                    <ul className="space-y-0.5">
                      {inGroup.map((item) => (
                        <li key={item.id}>
                          <div
                            role="button"
                            tabIndex={0}
                            data-library-item={item.id}
                            onKeyDown={(e) => onLibraryRowKeyDown(e, item)}
                            className={`flex w-full items-center gap-2 rounded-md px-1.5 py-1.5 text-left ${
                              item.available ? "cursor-pointer hover:bg-slate-50" : "cursor-not-allowed opacity-50"
                            }`}
                            onClick={() => item.available && item.onAdd()}
                          >
                            <span className="grid size-7 shrink-0 place-items-center rounded bg-slate-100 text-slate-600">
                              <item.icon size={14} />
                            </span>
                            <div className="min-w-0 flex-1">
                              <p className="text-[13px] font-medium leading-tight text-slate-900">{item.name}</p>
                              {item.badge ? (
                                <p className="mt-0.5 text-[10px] text-amber-800">{item.badge}</p>
                              ) : null}
                            </div>
                            <Button
                              type="button"
                              size="sm"
                              variant="secondary"
                              className="h-6 shrink-0 px-1.5 text-[10px]"
                              disabled={!item.available}
                              onClick={(e) => {
                                e.stopPropagation();
                                if (item.available) item.onAdd();
                              }}
                            >
                              {item.addLabel}
                            </Button>
                          </div>
                        </li>
                      ))}
                    </ul>
                  </li>
                );
              })}
            </ul>
          </aside>

          <div className="flex min-h-[min(360px,55vh)] min-w-0 flex-col overflow-hidden rounded-md border border-slate-200/90 bg-white lg:min-h-0">
            <AutomationNodeCanvas
              draft={draft}
              canvasLayout={draft.canvasLayout}
              onLayoutChange={(layout) => updateDraft({ canvasLayout: layout })}
              selectedStep={selectedStep}
              onSelectStep={(step) => {
                setSelectedStep(step);
                setInspectorTab("configure");
              }}
              validationIssueKeys={validationIssueKeys}
              memberNamesById={memberNamesById}
              aiAgentNamesById={aiAgentNamesById}
              canUndo={draftHistory.past.length > 0}
              canRedo={draftHistory.future.length > 0}
              onUndo={undoDraft}
              onRedo={redoDraft}
              onAddCondition={(at) => addConditionAt(at, "contains_keyword")}
              onAddAction={(at) => addActionAt(at)}
              onRemoveCondition={removeCondition}
              onRemoveAction={removeAction}
              onMoveCondition={moveCondition}
              onMoveAction={moveAction}
            />
          </div>

          <aside
            className="flex min-h-0 min-w-0 flex-col overflow-hidden rounded-md border border-slate-200/90 bg-white max-h-96 lg:max-h-none"
            aria-label="Inspector"
          >
            <div className="flex gap-1 border-b border-slate-100 p-1.5">
              <button
                type="button"
                className={`flex-1 rounded-md py-1.5 text-xs font-medium ${
                  inspectorTab === "configure" ? "bg-slate-100 text-slate-900" : "text-slate-500 hover:bg-slate-50"
                }`}
                onClick={() => setInspectorTab("configure")}
              >
                Configure
              </button>
              <button
                type="button"
                className={`flex-1 rounded-md py-1.5 text-xs font-medium ${
                  inspectorTab === "test" ? "bg-slate-100 text-slate-900" : "text-slate-500 hover:bg-slate-50"
                }`}
                onClick={() => setInspectorTab("test")}
              >
                Test
              </button>
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto p-3">
              {inspectorTab === "configure" && (
                <InspectorConfigure
                  draft={draft}
                  updateDraft={updateDraft}
                  selectedStep={selectedStep}
                  showValidation={showValidation}
                  draftValidation={draftValidation}
                  setShowValidation={setShowValidation}
                  members={members}
                  fieldClass={fieldClass}
                  onSelectErrorStep={scrollToStep}
                />
              )}
              {inspectorTab === "test" && (
                <InspectorTest
                  sampleMessage={sampleMessage}
                  setSampleMessage={setSampleMessage}
                  sampleTicketPriority={sampleTicketPriority}
                  setSampleTicketPriority={setSampleTicketPriority}
                  sampleTicketStatus={sampleTicketStatus}
                  setSampleTicketStatus={setSampleTicketStatus}
                  sampleChannel={sampleChannel}
                  setSampleChannel={setSampleChannel}
                  sampleFirstMessage={sampleFirstMessage}
                  setSampleFirstMessage={setSampleFirstMessage}
                  sampleAssigneePresent={sampleAssigneePresent}
                  setSampleAssigneePresent={setSampleAssigneePresent}
                  sampleConversationAiMode={sampleConversationAiMode}
                  setSampleConversationAiMode={setSampleConversationAiMode}
                  sampleShopifyConnected={sampleShopifyConnected}
                  setSampleShopifyConnected={setSampleShopifyConnected}
                  fieldClass={fieldClass}
                  previewResult={previewResult}
                  previewPending={preview.isPending}
                  onRunTest={handleTestWorkflow}
                  testDisabled={draftValidation.errors.length > 0 || !sampleMessage.trim()}
                  missingSample={!sampleMessage.trim()}
                />
              )}
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}

function InspectorConfigure({
  draft,
  updateDraft,
  selectedStep,
  showValidation,
  draftValidation,
  setShowValidation,
  members,
  fieldClass,
  onSelectErrorStep,
}: {
  draft: WorkflowDraft;
  updateDraft: (u: Partial<WorkflowDraft> | ((c: WorkflowDraft) => WorkflowDraft)) => void;
  selectedStep: DraftStep | null;
  showValidation: boolean;
  draftValidation: ReturnType<typeof validateWorkflowDraft>;
  setShowValidation: (v: boolean) => void;
  members: UseQueryResult<User[], Error>;
  fieldClass: string;
  onSelectErrorStep: (s: DraftStep) => void;
}) {
  const condIssues = (i: number) =>
    draftValidation.issues.filter((x) => x.step.type === "condition" && x.step.index === i).map((x) => x.message);
  const actIssues = (i: number) =>
    draftValidation.issues.filter((x) => x.step.type === "action" && x.step.index === i).map((x) => x.message);
  const trigIssues = draftValidation.issues.filter((x) => x.step.type === "trigger").map((x) => x.message);

  return (
    <div className="space-y-4">
      {!selectedStep && <p className="text-sm text-slate-500">Select a step on the canvas.</p>}
      {selectedStep?.type === "trigger" && (
        <div data-automation-step="trigger">
          <p className="text-xs font-semibold uppercase text-teal-700">Trigger</p>
          <p className="mt-1 text-sm font-semibold text-slate-900">Incoming customer message</p>
          <p className="mt-2 text-xs text-slate-500">
            Channel filters and “first message only” apply before conditions. Messaging integrations reuse this trigger with
            a channel filter.
          </p>
          <label className="mt-3 block text-sm font-medium text-slate-700">
            Channel filter (optional)
            <input
              value={draft.trigger.channel ?? ""}
              onChange={(e) =>
                updateDraft({
                  trigger: {
                    ...draft.trigger,
                    channel: e.target.value.trim() ? e.target.value : null,
                  },
                })
              }
              className={fieldClass}
              placeholder="e.g. widget, whatsapp, messenger"
            />
          </label>
          <label className="mt-2 flex items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={draft.trigger.first_message_only}
              onChange={(e) =>
                updateDraft({
                  trigger: { ...draft.trigger, first_message_only: e.target.checked },
                })
              }
            />
            First customer message in the conversation only
          </label>
          <label className="mt-3 block text-sm font-medium text-slate-700">
            AI agent filter (optional, UUID)
            <input
              value={draft.trigger.ai_agent_id ?? ""}
              onChange={(e) =>
                updateDraft({
                  trigger: {
                    ...draft.trigger,
                    ai_agent_id: e.target.value.trim() ? e.target.value.trim() : null,
                  },
                })
              }
              className={fieldClass}
              placeholder="Leave blank for all agents"
            />
          </label>
          <label className="mt-2 block text-sm font-medium text-slate-700">
            Channel connection filter (optional, UUID)
            <input
              value={draft.trigger.integration_connection_id ?? ""}
              onChange={(e) =>
                updateDraft({
                  trigger: {
                    ...draft.trigger,
                    integration_connection_id: e.target.value.trim() ? e.target.value.trim() : null,
                  },
                })
              }
              className={fieldClass}
              placeholder="e.g. WhatsApp connection id"
            />
          </label>
          {showValidation && trigIssues.map((m) => (
            <p key={m} role="alert" className="mt-2 text-xs text-red-700">
              {m}
            </p>
          ))}
        </div>
      )}

      {selectedStep?.type === "condition" && draft.conditions[selectedStep.index] != null && (
        <div data-automation-step={`condition-${selectedStep.index}`}>
          <p className="text-xs font-semibold uppercase text-amber-800">Condition {selectedStep.index + 1}</p>
          <label className="mt-2 block text-sm font-medium text-slate-700">
            Match logic (group)
            <select
              value={draft.conditionMode}
              onChange={(e) => updateDraft({ conditionMode: e.target.value as "all" | "any" })}
              className={fieldClass}
            >
              <option value="all">Match all conditions (AND)</option>
              <option value="any">Match any condition (OR)</option>
            </select>
          </label>
          <label className="mt-3 block text-sm font-medium text-slate-700">
            Rule type
            <select
              value={draft.conditions[selectedStep.index]!.kind}
              onChange={(e) => {
                const kind = e.target.value as Condition["kind"];
                updateDraft((c) => {
                  const next = [...c.conditions];
                  next[selectedStep.index] = defaultConditionForKind(kind);
                  return { ...c, conditions: next };
                });
              }}
              className={fieldClass}
            >
              <option value="contains_keyword">Message contains phrase</option>
              <option value="channel_is">Channel</option>
              <option value="ticket_priority_is">Ticket priority</option>
              <option value="ticket_status_is">Ticket status</option>
              <option value="conversation_ai_mode_is">Conversation AI mode</option>
              <option value="assignee_present">Assignee present</option>
              <option value="shopify_store_connected">Shopify store connected</option>
            </select>
          </label>
          {draft.conditions[selectedStep.index]!.kind === "contains_keyword" && (
            <label className="mt-3 block text-sm font-medium text-slate-700">
              Phrase
              <input
                aria-label={`Condition ${selectedStep.index + 1} · message contains`}
                value={(draft.conditions[selectedStep.index] as Extract<Condition, { kind: "contains_keyword" }>).value}
                onChange={(e) =>
                  updateDraft((c) => {
                    const next = [...c.conditions];
                    next[selectedStep.index] = { kind: "contains_keyword", value: e.target.value };
                    return { ...c, conditions: next };
                  })
                }
                className={fieldClass}
                placeholder="refund"
              />
            </label>
          )}
          {draft.conditions[selectedStep.index]!.kind === "channel_is" && (
            <>
              <label className="mt-3 block text-sm font-medium text-slate-700">
                Operator
                <select
                  value={(draft.conditions[selectedStep.index] as Extract<Condition, { kind: "channel_is" }>).operator}
                  onChange={(e) =>
                    updateDraft((c) => {
                      const next = [...c.conditions];
                      const cur = next[selectedStep.index] as Extract<Condition, { kind: "channel_is" }>;
                      next[selectedStep.index] = { ...cur, operator: e.target.value as "is" | "is_not" };
                      return { ...c, conditions: next };
                    })
                  }
                  className={fieldClass}
                >
                  <option value="is">Is</option>
                  <option value="is_not">Is not</option>
                </select>
              </label>
              <label className="mt-2 block text-sm font-medium text-slate-700">
                Channel
                <input
                  value={(draft.conditions[selectedStep.index] as Extract<Condition, { kind: "channel_is" }>).value}
                  onChange={(e) =>
                    updateDraft((c) => {
                      const next = [...c.conditions];
                      next[selectedStep.index] = { kind: "channel_is", operator: (next[selectedStep.index] as Extract<Condition, { kind: "channel_is" }>).operator, value: e.target.value };
                      return { ...c, conditions: next };
                    })
                  }
                  className={fieldClass}
                  placeholder="widget"
                />
              </label>
            </>
          )}
          {draft.conditions[selectedStep.index]!.kind === "ticket_priority_is" && (
            <>
              <label className="mt-3 block text-sm font-medium text-slate-700">
                Operator
                <select
                  value={(draft.conditions[selectedStep.index] as Extract<Condition, { kind: "ticket_priority_is" }>).operator}
                  onChange={(e) =>
                    updateDraft((c) => {
                      const next = [...c.conditions];
                      const cur = next[selectedStep.index] as Extract<Condition, { kind: "ticket_priority_is" }>;
                      next[selectedStep.index] = { ...cur, operator: e.target.value as "is" | "is_not" };
                      return { ...c, conditions: next };
                    })
                  }
                  className={fieldClass}
                >
                  <option value="is">Is</option>
                  <option value="is_not">Is not</option>
                </select>
              </label>
              <label className="mt-2 block text-sm font-medium text-slate-700">
                Priority
                <select
                  value={(draft.conditions[selectedStep.index] as Extract<Condition, { kind: "ticket_priority_is" }>).value}
                  onChange={(e) =>
                    updateDraft((c) => {
                      const next = [...c.conditions];
                      const cur = next[selectedStep.index] as Extract<Condition, { kind: "ticket_priority_is" }>;
                      next[selectedStep.index] = { ...cur, value: e.target.value as typeof cur.value };
                      return { ...c, conditions: next };
                    })
                  }
                  className={fieldClass}
                >
                  <option value="low">Low</option>
                  <option value="normal">Normal</option>
                  <option value="high">High</option>
                  <option value="urgent">Urgent</option>
                </select>
              </label>
            </>
          )}
          {draft.conditions[selectedStep.index]!.kind === "ticket_status_is" && (
            <>
              <label className="mt-3 block text-sm font-medium text-slate-700">
                Operator
                <select
                  value={(draft.conditions[selectedStep.index] as Extract<Condition, { kind: "ticket_status_is" }>).operator}
                  onChange={(e) =>
                    updateDraft((c) => {
                      const next = [...c.conditions];
                      const cur = next[selectedStep.index] as Extract<Condition, { kind: "ticket_status_is" }>;
                      next[selectedStep.index] = { ...cur, operator: e.target.value as "is" | "is_not" };
                      return { ...c, conditions: next };
                    })
                  }
                  className={fieldClass}
                >
                  <option value="is">Is</option>
                  <option value="is_not">Is not</option>
                </select>
              </label>
              <label className="mt-2 block text-sm font-medium text-slate-700">
                Ticket status
                <select
                  value={(draft.conditions[selectedStep.index] as Extract<Condition, { kind: "ticket_status_is" }>).value}
                  onChange={(e) =>
                    updateDraft((c) => {
                      const next = [...c.conditions];
                      const cur = next[selectedStep.index] as Extract<Condition, { kind: "ticket_status_is" }>;
                      next[selectedStep.index] = { ...cur, value: e.target.value };
                      return { ...c, conditions: next };
                    })
                  }
                  className={fieldClass}
                >
                  <option value="open">Open</option>
                  <option value="pending">Pending</option>
                  <option value="resolved">Resolved</option>
                  <option value="closed">Closed</option>
                </select>
              </label>
            </>
          )}
          {draft.conditions[selectedStep.index]!.kind === "conversation_ai_mode_is" && (
            <label className="mt-3 block text-sm font-medium text-slate-700">
              Mode
              <select
                value={(draft.conditions[selectedStep.index] as Extract<Condition, { kind: "conversation_ai_mode_is" }>).mode}
                onChange={(e) =>
                  updateDraft((c) => {
                    const next = [...c.conditions];
                    next[selectedStep.index] = {
                      kind: "conversation_ai_mode_is",
                      mode: e.target.value as "ai" | "human",
                    };
                    return { ...c, conditions: next };
                  })
                }
                className={fieldClass}
              >
                <option value="ai">AI</option>
                <option value="human">Human</option>
              </select>
            </label>
          )}
          {draft.conditions[selectedStep.index]!.kind === "assignee_present" && (
            <label className="mt-3 block text-sm font-medium text-slate-700">
              Expect assignee
              <select
                value={
                  (draft.conditions[selectedStep.index] as Extract<Condition, { kind: "assignee_present" }>).value
                    ? "yes"
                    : "no"
                }
                onChange={(e) =>
                  updateDraft((c) => {
                    const next = [...c.conditions];
                    next[selectedStep.index] = {
                      kind: "assignee_present",
                      value: e.target.value === "yes",
                    };
                    return { ...c, conditions: next };
                  })
                }
                className={fieldClass}
              >
                <option value="yes">Has assignee</option>
                <option value="no">Unassigned</option>
              </select>
            </label>
          )}
          {draft.conditions[selectedStep.index]!.kind === "shopify_store_connected" && (
            <p className="mt-3 text-xs text-slate-500">True when the workspace has an active Shopify installation.</p>
          )}
          {showValidation &&
            condIssues(selectedStep.index).map((m) => (
              <p key={m} role="alert" className="mt-2 text-xs text-red-700">
                {m}
              </p>
            ))}
        </div>
      )}

      {selectedStep?.type === "action" && draft.actions[selectedStep.index] != null && (
        <div data-automation-step={`action-${selectedStep.index}`}>
          <p className="text-xs font-semibold uppercase text-violet-700">Action {selectedStep.index + 1}</p>
          <label className="mt-2 block text-sm font-medium text-slate-700">
            Action type
            <select
              value={draft.actions[selectedStep.index]!.kind}
              onChange={(e) => {
                const kind = e.target.value as Action["kind"];
                updateDraft((c) => {
                  const next = [...c.actions];
                  next[selectedStep.index] = defaultActionForKind(kind);
                  return { ...c, actions: next };
                });
              }}
              className={fieldClass}
            >
              <option value="set_priority">Set ticket priority</option>
              <option value="assign_to_user">Assign to teammate</option>
              <option value="assign_to_team">Assign to support team</option>
              <option value="set_ticket_status">Set ticket status</option>
              <option value="set_conversation_ai_mode">Set conversation AI mode</option>
              <option value="route_to_ai_bot">Route to AI bot</option>
              <option value="restore_widget_bot_routing">Restore widget bot routing</option>
              <option value="add_internal_note">Add internal note</option>
              <option value="require_human_approval">Require Owner/Admin approval</option>
              <option value="lookup_shopify_order">Look up Shopify order (read-only)</option>
              <option value="search_shopify_catalog">Search Shopify catalog (read-only)</option>
              <option value="request_commerce_approval">Request cancellation review</option>
            </select>
          </label>
          {draft.actions[selectedStep.index]!.kind === "set_priority" && (
            <>
              <label className="mt-3 block text-sm font-medium text-slate-700">
                Priority
                <select
                  aria-label="Action priority"
                  value={(draft.actions[selectedStep.index] as Extract<Action, { kind: "set_priority" }>).value}
                  onChange={(e) =>
                    updateDraft((c) => {
                      const next = [...c.actions];
                      const cur = next[selectedStep.index] as Extract<Action, { kind: "set_priority" }>;
                      next[selectedStep.index] = { ...cur, value: e.target.value as typeof cur.value };
                      return { ...c, actions: next };
                    })
                  }
                  className={fieldClass}
                >
                  <option value="low">Low</option>
                  <option value="normal">Normal</option>
                  <option value="high">High</option>
                  <option value="urgent">Urgent</option>
                </select>
              </label>
              <label className="mt-2 flex items-center gap-2 text-sm text-slate-700">
                <input
                  type="checkbox"
                  checked={(draft.actions[selectedStep.index] as Extract<Action, { kind: "set_priority" }>).only_raise}
                  onChange={(e) =>
                    updateDraft((c) => {
                      const next = [...c.actions];
                      const cur = next[selectedStep.index] as Extract<Action, { kind: "set_priority" }>;
                      next[selectedStep.index] = { ...cur, only_raise: e.target.checked };
                      return { ...c, actions: next };
                    })
                  }
                />
                Only raise priority (never lower)
              </label>
            </>
          )}
          {draft.actions[selectedStep.index]!.kind === "assign_to_user" && (
            <>
              <label className="mt-3 block text-sm font-medium text-slate-700">
                Assign to
                <select
                  aria-label="Assign to teammate"
                  required
                  value={(draft.actions[selectedStep.index] as Extract<Action, { kind: "assign_to_user" }>).user_id}
                  onChange={(e) =>
                    updateDraft((c) => {
                      const next = [...c.actions];
                      const cur = next[selectedStep.index] as Extract<Action, { kind: "assign_to_user" }>;
                      next[selectedStep.index] = { ...cur, user_id: e.target.value };
                      return { ...c, actions: next };
                    })
                  }
                  className={fieldClass}
                >
                  <option value="">Choose teammate</option>
                  {members.data
                    ?.filter((member) => member.is_active && ["owner", "admin", "agent"].includes(member.role))
                    .map((member) => (
                      <option key={member.id} value={member.id}>
                        {member.full_name} · {member.role}
                      </option>
                    ))}
                </select>
              </label>
              <label className="mt-2 flex items-center gap-2 text-sm text-slate-700">
                <input
                  type="checkbox"
                  checked={(draft.actions[selectedStep.index] as Extract<Action, { kind: "assign_to_user" }>).only_if_unassigned}
                  onChange={(e) =>
                    updateDraft((c) => {
                      const next = [...c.actions];
                      const cur = next[selectedStep.index] as Extract<Action, { kind: "assign_to_user" }>;
                      next[selectedStep.index] = { ...cur, only_if_unassigned: e.target.checked };
                      return { ...c, actions: next };
                    })
                  }
                />
                Only if unassigned
              </label>
              {members.isError && (
                <span role="alert" className="mt-1 block text-xs text-red-700">
                  Unable to load teammates.
                </span>
              )}
            </>
          )}
          {draft.actions[selectedStep.index]!.kind === "assign_to_team" && (
            <>
              <label className="mt-3 block text-sm font-medium text-slate-700">
                Support team
                <select
                  aria-label="Assign to support team"
                  required
                  value={(draft.actions[selectedStep.index] as Extract<Action, { kind: "assign_to_team" }>).team_id}
                  onChange={(e) =>
                    updateDraft((c) => {
                      const next = [...c.actions];
                      const cur = next[selectedStep.index] as Extract<Action, { kind: "assign_to_team" }>;
                      next[selectedStep.index] = { ...cur, team_id: e.target.value };
                      return { ...c, actions: next };
                    })
                  }
                  className={fieldClass}
                >
                  <option value="">Choose support team</option>
                  {teams.data?.filter((team) => team.is_active).map((team) => (
                    <option key={team.id} value={team.id}>{team.name}</option>
                  ))}
                </select>
              </label>
              {teams.data?.every((team) => !team.is_active) && (
                <p className="mt-1 text-xs text-slate-500">Create an active support team in Settings before using this action.</p>
              )}
              <label className="mt-2 flex items-center gap-2 text-sm text-slate-700">
                <input
                  type="checkbox"
                  checked={(draft.actions[selectedStep.index] as Extract<Action, { kind: "assign_to_team" }>).only_if_unassigned}
                  onChange={(e) =>
                    updateDraft((c) => {
                      const next = [...c.actions];
                      const cur = next[selectedStep.index] as Extract<Action, { kind: "assign_to_team" }>;
                      next[selectedStep.index] = { ...cur, only_if_unassigned: e.target.checked };
                      return { ...c, actions: next };
                    })
                  }
                />
                Only if ticket has no team
              </label>
              {teams.isError && <span role="alert" className="mt-1 block text-xs text-red-700">Unable to load teams.</span>}
            </>
          )}
          {draft.actions[selectedStep.index]!.kind === "set_ticket_status" && (
            <label className="mt-3 block text-sm font-medium text-slate-700">
              Set ticket status
              <select
                value={(draft.actions[selectedStep.index] as Extract<Action, { kind: "set_ticket_status" }>).value}
                onChange={(e) =>
                  updateDraft((c) => {
                    const next = [...c.actions];
                    const cur = next[selectedStep.index] as Extract<Action, { kind: "set_ticket_status" }>;
                    next[selectedStep.index] = { ...cur, value: e.target.value };
                    return { ...c, actions: next };
                  })
                }
                className={fieldClass}
              >
                <option value="open">Open</option>
                <option value="pending">Pending</option>
                <option value="resolved">Resolved</option>
                <option value="closed">Closed</option>
              </select>
            </label>
          )}
          {draft.actions[selectedStep.index]!.kind === "set_conversation_ai_mode" && (
            <label className="mt-3 block text-sm font-medium text-slate-700">
              Mode
              <select
                value={(draft.actions[selectedStep.index] as Extract<Action, { kind: "set_conversation_ai_mode" }>).mode}
                onChange={(e) =>
                  updateDraft((c) => {
                    const next = [...c.actions];
                    const cur = next[selectedStep.index] as Extract<Action, { kind: "set_conversation_ai_mode" }>;
                    next[selectedStep.index] = { ...cur, mode: e.target.value as "ai" | "human" };
                    return { ...c, actions: next };
                  })
                }
                className={fieldClass}
              >
                <option value="ai">AI</option>
                <option value="human">Human</option>
              </select>
            </label>
          )}
          {draft.actions[selectedStep.index]!.kind === "route_to_ai_bot" && (
            <>
              <label className="mt-3 block text-sm font-medium text-slate-700">
                AI bot
                <select
                  aria-label="Route to AI bot"
                  required
                  value={(draft.actions[selectedStep.index] as Extract<Action, { kind: "route_to_ai_bot" }>).ai_agent_id}
                  onChange={(e) =>
                    updateDraft((c) => {
                      const next = [...c.actions];
                      const cur = next[selectedStep.index] as Extract<Action, { kind: "route_to_ai_bot" }>;
                      next[selectedStep.index] = { ...cur, ai_agent_id: e.target.value };
                      return { ...c, actions: next };
                    })
                  }
                  className={fieldClass}
                >
                  <option value="" disabled>
                    {aiAgents.isLoading ? "Loading active AI bots…" : "Choose an active AI bot"}
                  </option>
                  {aiAgents.data?.items
                    .filter((agent) => agent.status === "active")
                    .map((agent) => (
                      <option key={agent.id} value={agent.id}>
                        {agent.name}{agent.is_default ? " · default" : ""}
                      </option>
                    ))}
                </select>
              </label>
              <p className="mt-2 text-xs leading-5 text-slate-500">
                This applies to future widget messages after the workflow finishes. The current message may already have an AI reply queued.
              </p>
              {aiAgents.isError && (
                <span role="alert" className="mt-1 block text-xs text-red-700">
                  Unable to load AI bots. <button type="button" className="underline" onClick={() => void aiAgents.refetch()}>Try again</button>
                </span>
              )}
              {!aiAgents.isLoading && !aiAgents.isError && !(aiAgents.data?.items.some((agent) => agent.status === "active")) && (
                <p className="mt-1 text-xs text-amber-800">
                  Create or activate a bot in <Link href="/dashboard/ai/agents" className="underline">AI Bots</Link> before routing conversations.
                </p>
              )}
            </>
          )}
          {draft.actions[selectedStep.index]!.kind === "add_internal_note" && (
            <label className="mt-3 block text-sm font-medium text-slate-700">
              Note body
              <textarea
                rows={3}
                value={(draft.actions[selectedStep.index] as Extract<Action, { kind: "add_internal_note" }>).body}
                onChange={(e) =>
                  updateDraft((c) => {
                    const next = [...c.actions];
                    const cur = next[selectedStep.index] as Extract<Action, { kind: "add_internal_note" }>;
                    next[selectedStep.index] = { ...cur, body: e.target.value };
                    return { ...c, actions: next };
                  })
                }
                className={fieldClass}
                placeholder="Visible only to teammates"
              />
            </label>
          )}
          {draft.actions[selectedStep.index]!.kind === "require_human_approval" && (
            <>
              <p className="mt-3 rounded-lg bg-amber-50 p-2 text-xs leading-5 text-amber-900">
                This run pauses here. An Owner/Admin must approve or reject it from the Automations approval queue before later actions can continue.
              </p>
              <label className="mt-3 block text-sm font-medium text-slate-700">
                Approval summary
                <input
                  value={(draft.actions[selectedStep.index] as Extract<Action, { kind: "require_human_approval" }>).summary}
                  onChange={(e) =>
                    updateDraft((c) => {
                      const next = [...c.actions];
                      const cur = next[selectedStep.index] as Extract<Action, { kind: "require_human_approval" }>;
                      next[selectedStep.index] = { ...cur, summary: e.target.value };
                      return { ...c, actions: next };
                    })
                  }
                  className={fieldClass}
                  maxLength={200}
                />
              </label>
              <label className="mt-2 block text-sm font-medium text-slate-700">
                Details (optional)
                <textarea
                  rows={3}
                  value={(draft.actions[selectedStep.index] as Extract<Action, { kind: "require_human_approval" }>).detail ?? ""}
                  onChange={(e) =>
                    updateDraft((c) => {
                      const next = [...c.actions];
                      const cur = next[selectedStep.index] as Extract<Action, { kind: "require_human_approval" }>;
                      const detail = e.target.value.trim();
                      next[selectedStep.index] = { ...cur, detail: detail || null };
                      return { ...c, actions: next };
                    })
                  }
                  className={fieldClass}
                  maxLength={2000}
                  placeholder="Context for the reviewer"
                />
              </label>
            </>
          )}
          {draft.actions[selectedStep.index]!.kind === "lookup_shopify_order" && (
            <label className="mt-3 block text-sm font-medium text-slate-700">
              Order number regex
              <input
                value={(draft.actions[selectedStep.index] as Extract<Action, { kind: "lookup_shopify_order" }>).order_number_regex}
                onChange={(e) =>
                  updateDraft((c) => {
                    const next = [...c.actions];
                    const cur = next[selectedStep.index] as Extract<Action, { kind: "lookup_shopify_order" }>;
                    next[selectedStep.index] = { ...cur, order_number_regex: e.target.value };
                    return { ...c, actions: next };
                  })
                }
                className={fieldClass}
              />
            </label>
          )}
          {draft.actions[selectedStep.index]!.kind === "search_shopify_catalog" && (
            <>
              <label className="mt-3 block text-sm font-medium text-slate-700">
                Search regex (optional, first capture group)
                <input
                  value={
                    (draft.actions[selectedStep.index] as Extract<Action, { kind: "search_shopify_catalog" }>).query_regex ?? ""
                  }
                  onChange={(e) =>
                    updateDraft((c) => {
                      const next = [...c.actions];
                      const cur = next[selectedStep.index] as Extract<Action, { kind: "search_shopify_catalog" }>;
                      const v = e.target.value.trim();
                      next[selectedStep.index] = { ...cur, query_regex: v ? v : null };
                      return { ...c, actions: next };
                    })
                  }
                  className={fieldClass}
                  placeholder="e.g. recommend (.*)"
                />
              </label>
              <label className="mt-2 block text-sm font-medium text-slate-700">
                Max results
                <input
                  type="number"
                  min={1}
                  max={10}
                  value={(draft.actions[selectedStep.index] as Extract<Action, { kind: "search_shopify_catalog" }>).max_results}
                  onChange={(e) =>
                    updateDraft((c) => {
                      const next = [...c.actions];
                      const cur = next[selectedStep.index] as Extract<Action, { kind: "search_shopify_catalog" }>;
                      const n = Number(e.target.value);
                      next[selectedStep.index] = { ...cur, max_results: Number.isFinite(n) ? n : cur.max_results };
                      return { ...c, actions: next };
                    })
                  }
                  className={fieldClass}
                />
              </label>
            </>
          )}
          {draft.actions[selectedStep.index]!.kind === "request_commerce_approval" && (
            <>
              <p className="mt-3 rounded-lg bg-amber-50 p-2 text-xs leading-5 text-amber-900">
                This action creates a pending cancellation request only when the shopper has verified that exact order with an email code in this conversation. An Owner/Admin must approve it; no cancellation or refund happens automatically.
              </p>
              <label className="mt-3 block text-sm font-medium text-slate-700">
                Request summary
                <input
                  value={(draft.actions[selectedStep.index] as Extract<Action, { kind: "request_commerce_approval" }>).summary}
                  onChange={(e) =>
                    updateDraft((c) => {
                      const next = [...c.actions];
                      const cur = next[selectedStep.index] as Extract<Action, { kind: "request_commerce_approval" }>;
                      next[selectedStep.index] = { ...cur, summary: e.target.value };
                      return { ...c, actions: next };
                    })
                  }
                  className={fieldClass}
                />
              </label>
              <label className="mt-2 block text-sm font-medium text-slate-700">
                Order number pattern
                <input
                  value={(draft.actions[selectedStep.index] as Extract<Action, { kind: "request_commerce_approval" }>).order_number_regex}
                  onChange={(e) =>
                    updateDraft((c) => {
                      const next = [...c.actions];
                      const cur = next[selectedStep.index] as Extract<Action, { kind: "request_commerce_approval" }>;
                      next[selectedStep.index] = { ...cur, order_number_regex: e.target.value };
                      return { ...c, actions: next };
                    })
                  }
                  className={fieldClass}
                  placeholder="#?[A-Za-z0-9-]{4,}"
                />
                <span className="mt-1 block text-xs font-normal text-slate-500">Use a safe pattern to find the order number in the message. The backend matches it to the active email-verified order in this conversation and checks its current Shopify status.</span>
              </label>
              <label className="mt-2 block text-sm font-medium text-slate-700">
                Detail (optional)
                <textarea
                  rows={2}
                  value={
                    (draft.actions[selectedStep.index] as Extract<Action, { kind: "request_commerce_approval" }>).detail ?? ""
                  }
                  onChange={(e) =>
                    updateDraft((c) => {
                      const next = [...c.actions];
                      const cur = next[selectedStep.index] as Extract<Action, { kind: "request_commerce_approval" }>;
                      const v = e.target.value.trim();
                      next[selectedStep.index] = { ...cur, detail: v ? v : null };
                      return { ...c, actions: next };
                    })
                  }
                  className={fieldClass}
                />
              </label>
            </>
          )}
          {showValidation &&
            actIssues(selectedStep.index).map((m) => (
              <p key={m} role="alert" className="mt-2 text-xs text-red-700">
                {m}
              </p>
            ))}
        </div>
      )}

      <div className="border-t border-slate-100 pt-3">
        <button
          type="button"
          className="text-sm font-semibold text-teal-700 underline"
          onClick={() => setShowValidation(true)}
        >
          Validate entire workflow
        </button>
        {showValidation && draftValidation.errors.length === 0 && (
          <p role="status" className="mt-2 text-xs font-medium text-emerald-700">
            Draft structure is valid.
          </p>
        )}
        {showValidation && draftValidation.errors.length > 0 && (
          <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-red-800" role="alert">
            {draftValidation.issues.map((issue, i) => (
              <li key={i}>
                <button type="button" className="text-left underline" onClick={() => onSelectErrorStep(issue.step)}>
                  {issue.message}
                </button>
              </li>
            ))}
          </ul>
        )}
        {showValidation && draftValidation.warnings.length > 0 && (
          <ul className="mt-2 list-disc pl-5 text-xs text-amber-900" role="status">
            {draftValidation.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function InspectorTest({
  sampleMessage,
  setSampleMessage,
  sampleTicketPriority,
  setSampleTicketPriority,
  sampleTicketStatus,
  setSampleTicketStatus,
  sampleChannel,
  setSampleChannel,
  sampleFirstMessage,
  setSampleFirstMessage,
  sampleAssigneePresent,
  setSampleAssigneePresent,
  sampleConversationAiMode,
  setSampleConversationAiMode,
  sampleShopifyConnected,
  setSampleShopifyConnected,
  fieldClass,
  previewResult,
  previewPending,
  onRunTest,
  testDisabled,
  missingSample,
}: {
  sampleMessage: string;
  setSampleMessage: (v: string) => void;
  sampleTicketPriority: "" | "low" | "normal" | "high" | "urgent";
  setSampleTicketPriority: (v: "" | "low" | "normal" | "high" | "urgent") => void;
  sampleTicketStatus: string;
  setSampleTicketStatus: (v: string) => void;
  sampleChannel: string;
  setSampleChannel: (v: string) => void;
  sampleFirstMessage: boolean | null;
  setSampleFirstMessage: (v: boolean | null) => void;
  sampleAssigneePresent: boolean | null;
  setSampleAssigneePresent: (v: boolean | null) => void;
  sampleConversationAiMode: "" | "ai" | "human";
  setSampleConversationAiMode: (v: "" | "ai" | "human") => void;
  sampleShopifyConnected: boolean | null;
  setSampleShopifyConnected: (v: boolean | null) => void;
  fieldClass: string;
  previewResult: AutomationPreview | null;
  previewPending: boolean;
  onRunTest: () => void;
  testDisabled: boolean;
  missingSample: boolean;
}) {
  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-600">
        The preview uses the same condition evaluation as live runs. It never sends messages, changes tickets, or calls
        external systems.
      </p>
      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          size="sm"
          variant="secondary"
          onClick={() => setSampleMessage("I want a refund for order #12345")}
        >
          Refund request
        </Button>
        <Button
          type="button"
          size="sm"
          variant="secondary"
          onClick={() => setSampleMessage("Where is my order? I have not received shipping info.")}
        >
          Order status
        </Button>
      </div>
      <label className="block text-sm font-medium text-slate-700">
        Sample customer message
        <textarea
          aria-label="Sample customer message"
          value={sampleMessage}
          onChange={(e) => setSampleMessage(e.target.value)}
          maxLength={5000}
          rows={4}
          className={fieldClass}
          placeholder="Customer message text"
        />
      </label>
      <label className="block text-sm font-medium text-slate-700">
        Sample ticket priority
        <select
          aria-label="Sample ticket priority"
          value={sampleTicketPriority}
          onChange={(e) => setSampleTicketPriority(e.target.value as typeof sampleTicketPriority)}
          className={fieldClass}
        >
          <option value="">Not specified</option>
          <option value="low">Low</option>
          <option value="normal">Normal</option>
          <option value="high">High</option>
          <option value="urgent">Urgent</option>
        </select>
      </label>
      <label className="block text-sm font-medium text-slate-700">
        Sample ticket status
        <input
          value={sampleTicketStatus}
          onChange={(e) => setSampleTicketStatus(e.target.value)}
          className={fieldClass}
          placeholder="e.g. open"
        />
      </label>
      <label className="block text-sm font-medium text-slate-700">
        Sample channel
        <input
          value={sampleChannel}
          onChange={(e) => setSampleChannel(e.target.value)}
          className={fieldClass}
          placeholder="Should match trigger filter if set"
        />
      </label>
      <label className="block text-sm font-medium text-slate-700">
        First customer message?
        <select
          value={sampleFirstMessage === null ? "" : sampleFirstMessage ? "yes" : "no"}
          onChange={(e) => {
            const v = e.target.value;
            setSampleFirstMessage(v === "" ? null : v === "yes");
          }}
          className={fieldClass}
        >
          <option value="">Not specified</option>
          <option value="yes">Yes</option>
          <option value="no">No</option>
        </select>
      </label>
      <label className="block text-sm font-medium text-slate-700">
        Assignee present?
        <select
          value={sampleAssigneePresent === null ? "" : sampleAssigneePresent ? "yes" : "no"}
          onChange={(e) => {
            const v = e.target.value;
            setSampleAssigneePresent(v === "" ? null : v === "yes");
          }}
          className={fieldClass}
        >
          <option value="">Not specified</option>
          <option value="yes">Yes</option>
          <option value="no">No</option>
        </select>
      </label>
      <label className="block text-sm font-medium text-slate-700">
        Conversation AI mode (sample)
        <select
          value={sampleConversationAiMode}
          onChange={(e) => setSampleConversationAiMode(e.target.value as "" | "ai" | "human")}
          className={fieldClass}
        >
          <option value="">Not specified</option>
          <option value="ai">AI</option>
          <option value="human">Human</option>
        </select>
      </label>
      <label className="block text-sm font-medium text-slate-700">
        Shopify connected (sample)
        <select
          value={sampleShopifyConnected === null ? "" : sampleShopifyConnected ? "yes" : "no"}
          onChange={(e) => {
            const v = e.target.value;
            setSampleShopifyConnected(v === "" ? null : v === "yes");
          }}
          className={fieldClass}
        >
          <option value="">Not specified</option>
          <option value="yes">Yes</option>
          <option value="no">No</option>
        </select>
      </label>
      <div className="flex flex-wrap items-center gap-3">
        <Button type="button" variant="secondary" disabled={testDisabled || previewPending} onClick={onRunTest}>
          {previewPending ? "Running…" : "Run test"}
        </Button>
        {missingSample && <span className="text-xs text-amber-800">Enter a sample message to run the test.</span>}
      </div>
      {previewResult && (
        <div
          className={`rounded-xl p-3 text-sm ${previewResult.matches ? "bg-emerald-50 text-emerald-900" : "bg-amber-50 text-amber-900"}`}
        >
          <p className="font-semibold">
            {previewResult.matches ? "Workflow would match" : "Workflow would not match"}
          </p>
          <p className="mt-1 text-xs">
            Conditions ({previewResult.condition_mode === "all" ? "match all" : "match any"}):
          </p>
          <ul className="mt-1 space-y-1 text-xs">
            {previewResult.conditions.map((c, i) => (
              <li key={i}>
                {c.label}: {c.matched ? "matched" : "not matched"}
              </li>
            ))}
          </ul>
          {previewResult.steps && previewResult.steps.length > 0 && (
            <div className="mt-3 border-t border-black/5 pt-2">
              <p className="font-medium">Steps</p>
              <ul className="mt-1 space-y-1 text-xs">
                {previewResult.steps.map((s, i) => (
                  <li key={i} className={outcomeStyle(s.outcome)}>
                    <span className="font-semibold capitalize">{s.outcome.replace(/_/g, " ")}</span> · {s.step}
                    {s.detail ? ` — ${s.detail}` : ""}
                  </li>
                ))}
              </ul>
            </div>
          )}
          <div className="mt-3 border-t border-black/5 pt-2">
            <p className="font-medium">Planned actions</p>
            {previewResult.planned_actions.map((a, i) => (
              <p key={i} className="mt-1 text-xs">
                <span className="font-semibold capitalize">{a.outcome.replace(/_/g, " ")}</span>: {a.summary}
                {a.detail ? ` (${a.detail})` : ""}
              </p>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
