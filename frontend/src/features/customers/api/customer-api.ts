import { api } from "@/lib/api/client";
import type { Customer } from "../types/customer.types";
import type { Ticket } from "@/features/tickets/types/ticket.types";
import type { Page } from "@/types/pagination";
import type { z } from "zod";
import type { createCustomerSchema, updateCustomerSchema } from "../schemas/customer.schema";

export const customerQueryKeys = {
  all: ["customers"] as const,
  detail: (id: string) => ["customer", id] as const,
  tickets: (id: string) => ["customer-tickets", id] as const,
};

export const listCustomers = (params: string) => api<Page<Customer>>(`/customers?${params}`);
export const listCustomersForTicket = () => api<Page<Customer>>("/customers?limit=100");
export const createCustomer = (values: z.infer<typeof createCustomerSchema>) =>
  api<Customer>("/customers", { method: "POST", body: JSON.stringify(values) });
export const getCustomer = (id: string) => api<Customer>(`/customers/${id}`);
export const listCustomerTickets = (id: string) =>
  api<Page<Ticket>>(`/customers/${id}/tickets?limit=100`);
export const updateCustomer = (id: string, values: z.infer<typeof updateCustomerSchema>) =>
  api<Customer>(`/customers/${id}`, { method: "PATCH", body: JSON.stringify(values) });
