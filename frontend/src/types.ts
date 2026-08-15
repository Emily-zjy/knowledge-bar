export type UserMode = "guest" | "authenticated";

export type KnowledgeBaseOrigin = "guest" | "cloud";

export type KnowledgeBase = {
  id: string;
  user_id?: string;
  origin: KnowledgeBaseOrigin;
  name: string;
  description: string;
  color: string;
  tags?: string[];
  content_md: string;
  created_at: string;
  updated_at: string;
};

export type MindMapNode = {
  id: string;
  parentId: string | null;
  text: string;
  order: number;
};

export type MindMapData = {
  title: string;
  nodes: MindMapNode[];
};

export type ApiError = {
  code: string;
  message: string;
};

export type GenerateMindMapResponse = {
  generation_id: string;
  mind_map: MindMapData;
};

export type GenerationJobAccepted = {
  id: string;
  knowledge_base_id: string;
  status: "queued" | "running" | "succeeded" | "failed" | string;
  operation: "generate" | "regenerate" | string;
  client_request_id: string;
  created?: boolean;
};
