"use client";

import { Checkbox } from "@/components/ui";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Settings2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { Panel, PanelBody, PanelHeader } from "@/components/ui/panel";
import { recommendationQueryKeys, getRecommendationSettings, updateRecommendationSettings, type RecommendationSettingsInput } from "../api/recommendation-api";

const defaultValues: RecommendationSettingsInput = { enabled: true, mode: "automatic", max_products: 3, in_stock_only: false, excluded_product_ids: [], excluded_collection_ids: [], comparison_enabled: true, upselling_enabled: false, cross_selling_enabled: false, ranking_preferences: {}, human_handoff_preferences: { enabled: true, rejected_threshold: 3, unsupported_threshold: 2 } };

export function RecommendationSettingsCard() {
  const query = useQuery({ queryKey: recommendationQueryKeys.settings, queryFn: getRecommendationSettings });
  return <Panel>
    <PanelHeader title="Product recommendations" description="Control how the storefront assistant uses your synced catalog." action={<span className="grid size-9 place-items-center rounded-xl bg-violet-50 text-violet-700"><Settings2 size={18}/></span>}/>
    <PanelBody>{query.isPending ? <div role="status" className="h-24 animate-pulse rounded-xl bg-slate-100"/> : query.isError || !query.data ? <p role="alert" className="text-sm text-red-700">Recommendation settings could not be loaded.</p> : <RecommendationSettingsEditor initial={query.data} />}</PanelBody>
  </Panel>;
}

function RecommendationSettingsEditor({ initial }: { initial: import("../api/recommendation-api").RecommendationSettings }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<RecommendationSettingsInput>(() => ({
    enabled: initial.enabled ?? defaultValues.enabled,
    mode: initial.mode ?? defaultValues.mode,
    max_products: initial.max_products ?? defaultValues.max_products,
    in_stock_only: initial.in_stock_only ?? defaultValues.in_stock_only,
    excluded_product_ids: initial.excluded_product_ids ?? [],
    excluded_collection_ids: initial.excluded_collection_ids ?? [],
    comparison_enabled: initial.comparison_enabled ?? defaultValues.comparison_enabled,
    upselling_enabled: initial.upselling_enabled ?? defaultValues.upselling_enabled,
    cross_selling_enabled: initial.cross_selling_enabled ?? defaultValues.cross_selling_enabled,
    ranking_preferences: initial.ranking_preferences ?? {},
    human_handoff_preferences: initial.human_handoff_preferences ?? defaultValues.human_handoff_preferences,
  }));
  const [excludedProducts, setExcludedProducts] = useState((initial.excluded_product_ids ?? []).join(", "));
  const [excludedCollections, setExcludedCollections] = useState((initial.excluded_collection_ids ?? []).join(", "));
  const save = useMutation({ mutationFn: updateRecommendationSettings, onSuccess: async (saved) => { queryClient.setQueryData(recommendationQueryKeys.settings, saved); } });
  const toggle = (key: "enabled" | "in_stock_only" | "comparison_enabled" | "upselling_enabled" | "cross_selling_enabled") => setForm((value) => ({ ...value, [key]: !value[key] }));

  return <form className="space-y-5" onSubmit={(event) => { event.preventDefault(); save.mutate({ ...form, excluded_product_ids: excludedProducts.split(",").map((id) => id.trim()).filter(Boolean), excluded_collection_ids: excludedCollections.split(",").map((id) => id.trim()).filter(Boolean) }); }}>
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="flex items-center justify-between gap-3 rounded-xl bg-slate-50 p-3 text-sm font-medium">Recommendations enabled<Checkbox aria-label="Enable recommendations" checked={form.enabled} onCheckedChange={() => toggle("enabled")} className="size-4 accent-blue-600"/></label>
          <label className="flex items-center justify-between gap-3 rounded-xl bg-slate-50 p-3 text-sm font-medium">Only show in-stock products<Checkbox aria-label="In-stock only" checked={form.in_stock_only} onCheckedChange={() => toggle("in_stock_only")} className="size-4 accent-blue-600"/></label>
          <Field label="Recommendation mode"><Select value={form.mode} onChange={(event) => setForm((value) => ({ ...value, mode: event.target.value as RecommendationSettingsInput["mode"] }))}><option value="automatic">Automatic intent detection</option><option value="explicit">Explicit recommendation requests</option></Select></Field>
          <Field label="Maximum products"><Select value={form.max_products} onChange={(event) => setForm((value) => ({ ...value, max_products: Number(event.target.value) }))}>{[1, 2, 3, 4, 5].map((amount) => <option key={amount} value={amount}>{amount} products</option>)}</Select></Field>
        </div>
        <fieldset className="space-y-2"><legend className="text-sm font-semibold">Shopping actions</legend><div className="grid gap-2 sm:grid-cols-3">{([["comparison_enabled", "Compare products"], ["upselling_enabled", "Premium alternatives"], ["cross_selling_enabled", "Complementary items"]] as const).map(([key, title]) => <label key={key} className="flex items-center gap-2 rounded-xl border border-slate-200 p-3 text-sm"><Checkbox checked={form[key]} onCheckedChange={() => toggle(key)} className="size-4 accent-blue-600"/>{title}</label>)}</div><p className="text-xs text-slate-500">Comparison is supported. Upsell and cross-sell suggestions stay inactive until catalog compatibility workflows are available.</p></fieldset>
        <div className="grid gap-4 sm:grid-cols-2"><Field label="Excluded product IDs"><Input value={excludedProducts} onChange={(event) => setExcludedProducts(event.target.value)} placeholder="Paste comma-separated catalog IDs"/><small className="text-xs text-slate-500">Validated against this organization’s catalog.</small></Field><Field label="Excluded collection IDs"><Input value={excludedCollections} onChange={(event) => setExcludedCollections(event.target.value)} placeholder="Provider collection IDs, comma-separated"/><small className="text-xs text-slate-500">Applied when collection IDs are present in synced catalog metadata.</small></Field></div>
        <div className="grid gap-4 sm:grid-cols-3"><Field label="Feature match weight"><NumberInput min={0} max={100} value={form.ranking_preferences?.feature_match ?? 30} onChange={(value) => setWeight("feature_match", value)}/></Field><Field label="Brand preference weight"><NumberInput min={0} max={100} value={form.ranking_preferences?.brand ?? 10} onChange={(value) => setWeight("brand", value)}/></Field><Field label="Budget fit weight"><NumberInput min={0} max={100} value={form.ranking_preferences?.budget_fit ?? 15} onChange={(value) => setWeight("budget_fit", value)}/></Field></div>
        <div className="grid gap-4 sm:grid-cols-2"><Field label="Rejected recommendations before handoff"><NumberInput value={Number(form.human_handoff_preferences?.rejected_threshold ?? 3)} onChange={(value) => setForm((previous) => ({ ...previous, human_handoff_preferences: { ...previous.human_handoff_preferences, rejected_threshold: value } }))}/></Field><Field label="Unsupported requests before handoff"><NumberInput value={Number(form.human_handoff_preferences?.unsupported_threshold ?? 2)} onChange={(value) => setForm((previous) => ({ ...previous, human_handoff_preferences: { ...previous.human_handoff_preferences, unsupported_threshold: value } }))}/></Field></div>
        {save.isError && <p role="alert" className="text-sm text-red-700">Settings could not be saved. Check product IDs and values.</p>}{save.isSuccess && <p role="status" className="text-sm text-emerald-700">Recommendation settings saved.</p>}
        <Button type="submit" disabled={save.isPending}>{save.isPending ? "Saving…" : "Save recommendation settings"}</Button>
      </form>;

  function setWeight(key: string, weight: number) { setForm((previous) => ({ ...previous, ranking_preferences: { ...(previous.ranking_preferences ?? {}), [key]: weight } })); }
}

function Field({ label, children }: { label: string; children: React.ReactNode }) { return <label className="block space-y-1.5 text-sm font-medium text-slate-700"><span>{label}</span>{children}</label>; }
function NumberInput({ value, onChange, min = 1, max = 10 }: { value: number; onChange: (value: number) => void; min?: number; max?: number }) { return <Input type="number" min={min} max={max} value={value} onChange={(event) => onChange(Number(event.target.value))}/>; }
