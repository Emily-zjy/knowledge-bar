import type { GenerateMindMapResponse, MindMapData } from "../types";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

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
  requested_max_depth?: number;
}): Promise<GenerateMindMapResponse> {
  const response = await fetch(`${apiBaseUrl}/api/ai/mindmap/generate`, {
    method: "POST",
    headers: authHeaders(input.token, true),
    body: JSON.stringify({
      knowledge_base_id: input.knowledge_base_id,
      title: input.title,
      description: input.description,
      content_md: input.content_md,
      requested_max_depth: input.requested_max_depth ?? 5,
    }),
  });

  const payload = await response.json();
  if (!response.ok || !payload.success) {
    const message = payload?.error?.message || "生成失败，请稍后重试。";
    throw new Error(message);
  }

  return payload.data;
}

export async function regenerateMindMap(input: {
  knowledge_base_id: string;
  token: string;
  requested_max_depth?: number;
}): Promise<GenerateMindMapResponse> {
  const response = await fetch(`${apiBaseUrl}/api/ai/mindmap/${input.knowledge_base_id}/regenerate`, {
    method: "POST",
    headers: authHeaders(input.token, true),
    body: JSON.stringify({
      requested_max_depth: input.requested_max_depth ?? 5,
    }),
  });

  const payload = await response.json();
  if (!response.ok || !payload.success) {
    throw new Error(payload?.error?.message || "重新生成失败，请稍后重试。");
  }
  return payload.data;
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
}): Promise<{ id: string; status: string; error_code?: string; error_message?: string }> {
  const response = await fetch(`${apiBaseUrl}/api/ai/mindmap/jobs/${input.job_id}`, {
    headers: authHeaders(input.token),
  });

  const payload = await response.json();
  if (!response.ok || !payload.success) {
    throw new Error(payload?.error?.message || "获取任务状态失败。");
  }
  return payload.data;
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
