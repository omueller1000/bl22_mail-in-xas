import type { Role } from "../api/client";

const RANK: Record<Role, number> = { user: 0, operator: 1, admin: 2 };

export const ROLES: Role[] = ["user", "operator", "admin"];

/** Whether `actual` grants at least the privileges of `required` (User < Operator < Admin). */
export function hasRole(actual: Role, required: Role): boolean {
  return RANK[actual] >= RANK[required];
}

export const ROLE_LABELS: Record<Role, string> = {
  user: "User",
  operator: "Operator",
  admin: "Admin",
};
