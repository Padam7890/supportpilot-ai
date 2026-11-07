import { WorkflowDetailClient } from "../workflow-detail";

export default async function AutomationWorkflowDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <WorkflowDetailClient workflowId={id} />;
}
