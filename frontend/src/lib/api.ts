import type { GenerateMindMapResponse, MindMapData } from "../types";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

export async function generateMindMap(input: {
  knowledge_base_id: string;
  title: string;
  description: string;
  content_md: string;
  token?: string;
  guestSessionId?: string;
}): Promise<GenerateMindMapResponse> {
  const headers: HeadersInit = {
    "Content-Type": "application/json",
  };

  if (input.token) {
    headers.Authorization = `Bearer ${input.token}`;
  }

  if (input.guestSessionId) {
    headers["X-Guest-Session-Id"] = input.guestSessionId;
  }

  const response = await fetch(`${apiBaseUrl}/api/ai/mindmap/generate`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      knowledge_base_id: input.knowledge_base_id,
      title: input.title,
      description: input.description,
      content_md: input.content_md,
    }),
  });

  const payload = await response.json();
  if (!response.ok || !payload.success) {
    const message = payload?.error?.message || "生成失败，请稍后重试。";
    throw new Error(message);
  }

  return payload.data;
}

export async function exportWordDocument(input: {
  title: string;
  markdown: string;
  token?: string;
}): Promise<Blob> {
  const headers: HeadersInit = {
    "Content-Type": "application/json",
  };

  if (input.token) {
    headers.Authorization = `Bearer ${input.token}`;
  }

  const response = await fetch(`${apiBaseUrl}/api/ai/export/word`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      title: input.title,
      markdown: input.markdown,
    }),
  });

  if (!response.ok) {
    throw new Error("导出 Word 失败，请稍后重试。");
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
