// Compatibility barrel for shared consumers. Domain contracts live with their feature.
export type { User } from "@/features/auth/types/user.types";
export type { Invitation } from "@/features/organization/types/invitation.types";
export type { Customer } from "@/features/customers/types/customer.types";
export type { Ticket, TicketActivity, TicketStats } from "@/features/tickets/types/ticket.types";
export type { Conversation, Message } from "@/features/conversations/types/conversation.types";
export type { Page } from "@/types/pagination";
