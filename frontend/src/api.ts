import { useQuery } from "@tanstack/react-query";
import type { components } from "./schema";

type Schemas = components["schemas"];
export type Content = Schemas["RecipeContent"];
export type Recipe = Schemas["RecipeOut"];
export type Summary = Schemas["RecipeSummary"];
export type Me = Schemas["MeOut"];
export type Comment = Schemas["CommentOut"];
export type RevisionSummary = Schemas["RevisionSummary"];
export type Revision = Schemas["RevisionOut"];
export type Invite = Schemas["InviteOut"];
export type InviteCreated = Schemas["InviteCreatedOut"];
export type AdminUser = Schemas["AdminUserOut"];
export type RecipePage = Schemas["RecipePage"];
export type Tag = Schemas["TagOut"];
export type AuthConfig = Schemas["AuthConfigOut"];
export type Imported = Schemas["ImportOut"];
export type User = Schemas["UserOut"];

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

type Problem = { loc: (string | number)[]; msg: string };

export async function api<T = void>(path: string, method = "GET", body?: unknown): Promise<T> {
  const form = body instanceof FormData;
  const response = await fetch(`/api/${path}`, {
    method,
    headers: body !== undefined && !form ? { "Content-Type": "application/json" } : undefined,
    body: form ? body : body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    const detail = data?.detail;
    const message = Array.isArray(detail)
      ? detail.map((p: Problem) => `${p.loc.slice(1).join(" › ")}: ${p.msg}`).join("\n")
      : (detail ?? `Something went wrong (${response.status})`);
    throw new ApiError(response.status, message);
  }
  return response.status === 204 ? (undefined as T) : response.json();
}

/** Query keys are the API path, so invalidating is always by path. */
export function useApi<T>(path: string, enabled = true) {
  return useQuery({ queryKey: [path], queryFn: () => api<T>(path), enabled });
}

export const imageUrl = (id: string) => `/api/images/${id}`;
