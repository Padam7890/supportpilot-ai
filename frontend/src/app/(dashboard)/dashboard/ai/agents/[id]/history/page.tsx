import { redirect } from "next/navigation";

export default async function AIAgentHistoryRoute({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  redirect(`/dashboard/ai/agents/${id}/performance`);
}
