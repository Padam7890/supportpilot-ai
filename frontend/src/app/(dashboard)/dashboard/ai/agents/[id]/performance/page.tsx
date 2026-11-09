import { AIAgentPerformancePage } from "@/features/ai/components/ai-agent-performance-page";

export default async function AIAgentPerformanceRoute({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <AIAgentPerformancePage agentId={id} />;
}
