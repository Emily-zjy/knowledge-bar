import type { GenerateMindMapResponse, MindMapData } from "../types";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

export class ApiRequestError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "ApiRequestError";
  }
}

async function readJsonResponse(response: Response): Promise<Record<string, any>> {
  try {
    return await response.json();
  } catch {
    throw new ApiRequestError("INVALID_API_RESPONSE", "AI 返回结果异常，请重新生成。", response.status);
  }
}

async function readApiError(response: Response): Promise<string> {
  try {
    const payload = await response.json();
    return payload?.error?.message || payload?.detail || "请求失败，请稍后重试。";
  } catch {
    return "请求失败，请稍后重试。";
  }
}

function authHeaders(token: string | undefined, json = false): HeadersInit {
  const headers: HeadersInit = {};
  if (json) headers["Content-Type"] = "application/json";
  if (token) headers["Authorization"] = `Bearer ${token}`;
  return headers;
}

export async function generateMindMap(input: {
  knowledge_base_id: string;
  title: string;
  description: string;
  content_md: string;
  token: string;
  requested_max_depth: number;
  client_request_id: string;
  onJobStatus?: (status: string) => void;
  signal?: AbortSignal;
}): Promise<GenerateMindMapResponse> {
  const response = await fetch(`${apiBaseUrl}/api/ai/mindmap/generate`, {
    method: "POST",
    headers: authHeaders(input.token, true),
    body: JSON.stringify({
      knowledge_base_id: input.knowledge_base_id,
      title: input.title,
      description: input.description,
      content_md: input.content_md,
      requested_max_depth: input.requested_max_depth,
      client_request_id: input.client_request_id,
    }),
    signal: input.signal,
  });

  const payload = await readJsonResponse(response);
  if (!response.ok || !payload.success) {
    const message = payload?.error?.message || "生成失败，请稍后重试。";
    throw new ApiRequestError(payload?.error?.code || "REQUEST_FAILED", message, response.status);
  }

  if (payload.data?.mind_map) return payload.data;
  input.onJobStatus?.(String(payload.data?.status || "queued"));
  return waitForGenerationJob({
    job_id: String(payload.data?.id || ""),
    token: input.token,
    onJobStatus: input.onJobStatus,
    signal: input.signal,
  });
}

export async function regenerateMindMap(input: {
  knowledge_base_id: string;
  token: string;
  requested_max_depth: number;
  content_md?: string;
  client_request_id: string;
  onJobStatus?: (status: string) => void;
  signal?: AbortSignal;
}): Promise<GenerateMindMapResponse> {
  const body: Record<string, unknown> = {
    requested_max_depth: input.requested_max_depth,
  };
  if (input.content_md) {
    body.content_md = input.content_md;
  }
  body.client_request_id = input.client_request_id;
  const response = await fetch(`${apiBaseUrl}/api/ai/mindmap/${input.knowledge_base_id}/regenerate`, {
    method: "POST",
    headers: authHeaders(input.token, true),
    body: JSON.stringify(body),
    signal: input.signal,
  });

  const payload = await readJsonResponse(response);
  if (!response.ok || !payload.success) {
    throw new ApiRequestError(
      payload?.error?.code || "REQUEST_FAILED",
      payload?.error?.message || "重新生成失败，请稍后重试。",
      response.status,
    );
  }
  if (payload.data?.mind_map) return payload.data;
  input.onJobStatus?.(String(payload.data?.status || "queued"));
  return waitForGenerationJob({
    job_id: String(payload.data?.id || ""),
    token: input.token,
    onJobStatus: input.onJobStatus,
    signal: input.signal,
  });
}

export type LatestMindMapResponse = {
  id: string;
  knowledge_base_id: string;
  version_no: number;
  mind_map: MindMapData;
  markdown: string;
  updated_at: string | null;
};

export async function getLatestMindMap(input: {
  knowledge_base_id: string;
  token: string;
}): Promise<LatestMindMapResponse> {
  const response = await fetch(`${apiBaseUrl}/api/ai/mindmap/latest/${input.knowledge_base_id}`, {
    headers: authHeaders(input.token),
  });

  const payload = await response.json();
  if (!response.ok || !payload.success) {
    throw new Error(payload?.error?.message || "获取导图失败。");
  }
  return payload.data;
}

export type MindMapVersionItem = {
  id: string;
  version_no: number;
  updated_at: string | null;
};

export async function listMindMapVersions(input: {
  knowledge_base_id: string;
  token: string;
}): Promise<MindMapVersionItem[]> {
  const response = await fetch(`${apiBaseUrl}/api/ai/mindmap/versions/${input.knowledge_base_id}`, {
    headers: authHeaders(input.token),
  });

  const payload = await response.json();
  if (!response.ok || !payload.success) {
    throw new Error(payload?.error?.message || "获取版本列表失败。");
  }
  return payload.data.versions;
}

export async function patchMindMap(input: {
  mind_map_id: string;
  token: string;
  title?: string;
  update_node?: { id: string; text: string };
}): Promise<LatestMindMapResponse> {
  const body: Record<string, unknown> = {};
  if (input.title) body.title = input.title;
  if (input.update_node) body.update_node = input.update_node;

  const response = await fetch(`${apiBaseUrl}/api/ai/mindmap/${input.mind_map_id}`, {
    method: "PATCH",
    headers: authHeaders(input.token, true),
    body: JSON.stringify(body),
  });

  const payload = await response.json();
  if (!response.ok || !payload.success) {
    throw new Error(payload?.error?.message || "修改导图失败。");
  }
  return payload.data;
}

export async function deleteMindMap(input: {
  mind_map_id: string;
  token: string;
}): Promise<void> {
  const response = await fetch(`${apiBaseUrl}/api/ai/mindmap/${input.mind_map_id}`, {
    method: "DELETE",
    headers: authHeaders(input.token),
  });

  const payload = await response.json();
  if (!response.ok || !payload.success) {
    throw new Error(payload?.error?.message || "删除导图失败。");
  }
}

export async function getGenerationJob(input: {
  job_id: string;
  token: string;
}): Promise<{
  id: string;
  status: string;
  operation?: string;
  knowledge_base_id?: string;
  error_code?: string;
  error_message?: string;
  error_stage?: string;
  result_mind_map_id?: string;
  requested_depth?: number;
  actual_depth?: number;
  queue_wait_ms?: number;
  generation_latency_ms?: number;
  total_latency_ms?: number;
  retry_count?: number;
  llm_call_count?: number;
  provider_status?: number;
}> {
  const response = await fetch(`${apiBaseUrl}/api/ai/mindmap/jobs/${input.job_id}`, {
    headers: authHeaders(input.token),
  });

  const payload = await response.json();
  if (!response.ok || !payload.success) {
    throw new Error(payload?.error?.message || "获取任务状态失败。");
  }
  return payload.data;
}

export async function getActiveGenerationJob(input: {
  knowledge_base_id: string;
  token: string;
}): Promise<Awaited<ReturnType<typeof getGenerationJob>> | null> {
  const response = await fetch(`${apiBaseUrl}/api/ai/mindmap/jobs/active/${input.knowledge_base_id}`, {
    headers: authHeaders(input.token),
  });
  const payload = await response.json();
  if (!response.ok || !payload.success) {
    throw new Error(payload?.error?.message || "获取任务状态失败。");
  }
  return payload.data;
}

export async function waitForGenerationJob(input: {
  job_id: string;
  token: string;
  onJobStatus?: (status: string) => void;
  signal?: AbortSignal;
}): Promise<GenerateMindMapResponse> {
  if (!input.job_id) throw new ApiRequestError("QUEUE_JOB_MISSING", "生成任务未创建。", 502);
  let delayMs = 1500;
  while (true) {
    if (input.signal?.aborted) throw new DOMException("Generation polling cancelled", "AbortError");
    const job = await getGenerationJob({ job_id: input.job_id, token: input.token });
    input.onJobStatus?.(job.status);
    if (job.status === "succeeded") {
      return { generation_id: input.job_id, mind_map: {} as MindMapData };
    }
    if (job.status === "failed") {
      throw new ApiRequestError(
        job.error_code || job.error_stage || "GENERATION_FAILED",
        job.error_message || "AI 服务暂时繁忙，请稍后再试。",
        502,
      );
    }
    await waitForGenerationPollDelay(delayMs, input.signal);
    delayMs = Math.min(3000, Math.round(delayMs * 1.25));
  }
}

async function waitForGenerationPollDelay(delayMs: number, signal?: AbortSignal): Promise<void> {
  if (signal?.aborted) throw new DOMException("Generation polling cancelled", "AbortError");

  // A hidden/background mobile tab should not keep making frequent requests.
  // When the page becomes visible, resolve immediately so the next poll is a
  // fresh server read instead of trusting stale client state.
  const hidden = typeof document !== "undefined" && document.visibilityState === "hidden";
  const waitMs = hidden ? Math.max(delayMs, 8000) : delayMs;
  await new Promise<void>((resolve, reject) => {
    let settled = false;
    const timer = window.setTimeout(finish, waitMs);
    const onAbort = () => finish(new DOMException("Generation polling cancelled", "AbortError"), true);
    const onVisibility = () => {
      if (document.visibilityState === "visible") finish();
    };
    const cleanup = () => {
      window.clearTimeout(timer);
      signal?.removeEventListener("abort", onAbort);
      if (typeof document !== "undefined") document.removeEventListener("visibilitychange", onVisibility);
    };
    function finish(error?: DOMException, rejected = false) {
      if (settled) return;
      settled = true;
      cleanup();
      if (rejected && error) reject(error);
      else resolve();
    }
    signal?.addEventListener("abort", onAbort, { once: true });
    if (typeof document !== "undefined") document.addEventListener("visibilitychange", onVisibility);
  });
}

export async function exportMarkdown(input: {
  knowledge_base_id: string;
  token: string;
}): Promise<Blob> {
  const response = await fetch(`${apiBaseUrl}/api/ai/export/markdown/${input.knowledge_base_id}`, {
    headers: authHeaders(input.token),
  });

  if (!response.ok) {
    throw new Error(await readApiError(response));
  }
  return response.blob();
}

export async function exportWordDocument(input: {
  title: string;
  markdown: string;
  knowledgeBaseId?: string;
  token?: string;
}): Promise<Blob> {
  const headers: HeadersInit = { "Content-Type": "application/json" };
  if (input.token) headers["Authorization"] = `Bearer ${input.token}`;

  const response = await fetch(`${apiBaseUrl}/api/ai/export/word`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      title: input.title,
      markdown: input.markdown,
      knowledge_base_id: input.knowledgeBaseId,
    }),
  });

  if (!response.ok) {
    throw new Error(await readApiError(response));
  }

  return response.blob();
}

export function mindMapToMarkdown(mindMap: MindMapData): string {
  const childrenByParent = new Map<string | null, MindMapData["nodes"]>();
  for (const node of mindMap.nodes) {
    const list = childrenByParent.get(node.parentId) || [];
    list.push(node);
    childrenByParent.set(node.parentId, list);
  }

  for (const list of childrenByParent.values()) {
    list.sort((a, b) => a.order - b.order);
  }

  const render = (parentId: string | null, level: number): string[] => {
    const nodes = childrenByParent.get(parentId) || [];
    return nodes.flatMap((node) => [
      `${"  ".repeat(Math.max(level - 1, 0))}${level === 0 ? "# " : "- "}${node.text}`,
      ...render(node.id, level + 1),
    ]);
  };

  return render(null, 0).join("\n");
}
