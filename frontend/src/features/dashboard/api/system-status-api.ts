import { api } from "@/lib/api/client";

export type ReadinessStatus = {
  status: "ready";
  checks: {
    database: "connected";
    redis: "connected";
  };
};

export type WorkerHealth = {
  status: "active" | "inactive";
  active_workers: number;
  checked_at: string;
};

export const getSystemReadiness = () => api<ReadinessStatus>("/health/ready");
export const getWorkerHealth = () => api<WorkerHealth>("/health/worker");
