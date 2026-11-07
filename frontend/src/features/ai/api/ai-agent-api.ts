import { api } from "@/lib/api/client";
import type { components } from "@/lib/api/generated";

export type AIAgent = components["schemas"]["AIAgentOut"];
export type AIAgentPage = components["schemas"]["AIAgentPage"];
export type AIAgentAuditPage = components["schemas"]["AIAgentAuditPage"];
export type AIAgentTool = NonNullable<AIAgent["allowed_tools"]>[number];
export const aiAgentsKey = ["ai-agents"] as const;
export const aiAgentAuditKey = (id: string | undefined) => ["ai-agent-audit", id] as const;

export const listAIAgents = () => api<AIAgentPage>("/ai/agents?limit=100");
export const createAIAgent = (values: { name: string; system_instructions: string; knowledge_base_ids: string[]; allowed_tools: AIAgentTool[] }) =>
  api<AIAgent>("/ai/agents", { method: "POST", body: JSON.stringify(values) });
export const updateAIAgent = (id: string, values: { name: string; system_instructions: string; knowledge_base_ids?: string[]; allowed_tools?: AIAgentTool[] }) =>
  api<AIAgent>(`/ai/agents/${encodeURIComponent(id)}`, { method: "PUT", body: JSON.stringify(values) });
export const assignKnowledgeBases = (id: string, knowledge_base_ids: string[]) =>
  api<AIAgent>(`/ai/agents/${encodeURIComponent(id)}/knowledge-bases`, { method: "PUT", body: JSON.stringify({ knowledge_base_ids }) });
export const activateAIAgent = (id: string) => api<AIAgent>(`/ai/agents/${encodeURIComponent(id)}/activate`, { method: "POST" });
export const deactivateAIAgent = (id: string) => api<AIAgent>(`/ai/agents/${encodeURIComponent(id)}/deactivate`, { method: "POST" });
export const makeAIAgentDefault = (id: string) => api<AIAgent>(`/ai/agents/${encodeURIComponent(id)}/make-default`, { method: "POST" });
export const getAIAgentAudit = (id: string) => api<AIAgentAuditPage>(`/ai/agents/${encodeURIComponent(id)}/audit?limit=20`);
