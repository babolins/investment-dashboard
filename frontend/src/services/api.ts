import type {
  AllocationBreakdown,
  ConfigSummary,
  RebalanceRequest,
  RebalanceResult,
  UploadResponse,
} from "../types";

const BASE_URL = import.meta.env.VITE_API_URL ?? "";

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body.detail ?? JSON.stringify(body);
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export async function uploadPortfolio(file: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE_URL}/api/upload`, { method: "POST", body: form });
  return handleResponse<UploadResponse>(res);
}

export async function fetchRebalance(
  allocation: AllocationBreakdown,
  request: RebalanceRequest
): Promise<RebalanceResult> {
  const res = await fetch(`${BASE_URL}/api/rebalance`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...request, ...allocation }),
  });
  return handleResponse<RebalanceResult>(res);
}

export async function fetchConfig(): Promise<ConfigSummary> {
  const res = await fetch(`${BASE_URL}/api/config`);
  return handleResponse<ConfigSummary>(res);
}
