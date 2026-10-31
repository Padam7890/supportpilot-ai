import { api } from "@/lib/api/client";

export type ReadinessStatus = {
  status: "ready";
  checks: {
    database: "connected";
    redis: "connected";
  };
};

export const getSystemReadiness = () => api<ReadinessStatus>("/health/ready");
