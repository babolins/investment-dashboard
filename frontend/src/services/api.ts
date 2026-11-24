/** Typed client for the backend API. */
import type {
  AllocationBreakdown,
  AssignmentUpdate,
  CategoryInput,
  ConfigSummary,
  GroupInput,
  PortfolioSnapshot,
  RebalanceRequest,
  RebalanceResult,
  UploadResponse,
} from "../types";

const BASE_URL = import.meta.env.VITE_API_URL ?? "";

/** Extracts a readable message from FastAPI's `detail` (a string, or a list of validation errors). */
function describeDetail(detail: unknown): string | null {
  if (typeof detail === "string") return detail;
  if (!Array.isArray(detail)) return null;
  const messages = detail
    .map((item) => (typeof item?.msg === "string" ? item.msg.replace(/^Value error, /, "") : ""))
    .filter(Boolean);
  return messages.length > 0 ? messages.join("; ") : null;
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let message = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      message = describeDetail(body.detail) ?? message;
    } catch {
      /* ignore */
    }
    throw new Error(message);
  }
  return res.json() as Promise<T>;
}

/** Sends a request (JSON body when given) and parses the JSON response. */
async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method };
  if (body !== undefined) {
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify(body);
  }
  return handleResponse<T>(await fetch(`${BASE_URL}${path}`, init));
}

export async function uploadPortfolio(file: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE_URL}/api/upload`, { method: "POST", body: form });
  return handleResponse<UploadResponse>(res);
}

export function fetchAllocation(portfolio: PortfolioSnapshot): Promise<AllocationBreakdown> {
  return request("POST", "/api/allocation", portfolio);
}

export function fetchRebalance(
  allocation: AllocationBreakdown,
  rebalanceRequest: RebalanceRequest,
): Promise<RebalanceResult> {
  return request("POST", "/api/rebalance", { ...rebalanceRequest, ...allocation });
}

export function fetchConfig(): Promise<ConfigSummary> {
  return request("GET", "/api/config");
}

export function createCategory(input: CategoryInput): Promise<ConfigSummary> {
  return request("POST", "/api/categories", input);
}

export function updateCategory(
  name: string,
  patch: Partial<CategoryInput>,
): Promise<ConfigSummary> {
  return request("PATCH", `/api/categories/${encodeURIComponent(name)}`, patch);
}

export function deleteCategory(name: string): Promise<ConfigSummary> {
  return request("DELETE", `/api/categories/${encodeURIComponent(name)}`);
}

export function createGroup(input: GroupInput): Promise<ConfigSummary> {
  return request("POST", "/api/groups", input);
}

export function updateGroup(name: string, patch: Partial<GroupInput>): Promise<ConfigSummary> {
  return request("PATCH", `/api/groups/${encodeURIComponent(name)}`, patch);
}

export function deleteGroup(name: string): Promise<ConfigSummary> {
  return request("DELETE", `/api/groups/${encodeURIComponent(name)}`);
}

export function setAssignment(symbol: string, update: AssignmentUpdate): Promise<ConfigSummary> {
  return request("PUT", `/api/assignments/${encodeURIComponent(symbol)}`, update);
}
