import type { Session } from "@supabase/supabase-js";
import type { KnowledgeBase } from "../types";
import { hasSupabaseConfig, supabase } from "./supabase";

function assertClient() {
  if (!hasSupabaseConfig || !supabase) {
    throw new Error("Supabase 尚未配置。");
  }
  return supabase;
}

export async function getCloudSession(): Promise<Session | null> {
  if (!hasSupabaseConfig || !supabase) return null;
  const { data, error } = await supabase.auth.getSession();
  if (error) throw error;
  return data.session;
}

export async function signInWithEmail(email: string, password: string): Promise<Session> {
  const client = assertClient();
  const { data, error } = await client.auth.signInWithPassword({ email, password });
  if (error) throw error;
  if (!data.session) throw new Error("登录失败，请检查邮箱和密码。");
  return data.session;
}

export async function signUpWithEmail(email: string, password: string): Promise<Session | null> {
  const client = assertClient();
  const { data, error } = await client.auth.signUp({ email, password });
  if (error) throw error;
  return data.session;
}

export async function signOutCloud(): Promise<void> {
  if (!hasSupabaseConfig || !supabase) return;
  const { error } = await supabase.auth.signOut();
  if (error) throw error;
}

export async function listCloudKnowledgeBases(userId: string): Promise<KnowledgeBase[]> {
  const client = assertClient();
  const { data: bases, error } = await client
    .from("knowledge_bases")
    .select("*")
    .eq("user_id", userId)
    .order("updated_at", { ascending: false });
  if (error) throw error;

  const ids = (bases || []).map((item) => item.id);
  const tagMap = new Map<string, string[]>();
  if (ids.length > 0) {
    const { data: tagRows, error: tagError } = await client
      .from("knowledge_base_tags")
      .select("knowledge_base_id, selected_text, tags(name)")
      .in("knowledge_base_id", ids);
    if (tagError) throw tagError;

    for (const row of tagRows || []) {
      const key = row.knowledge_base_id as string;
      const current = tagMap.get(key) || [];
      const joinedTags = row.tags as { name: string } | Array<{ name: string }> | null;
      const tagRecord = Array.isArray(joinedTags) ? joinedTags[0] : joinedTags;
      const tagName = (row.selected_text || tagRecord?.name || "").trim();
      if (tagName) {
        current.push(tagName);
      }
      tagMap.set(key, Array.from(new Set(current)));
    }
  }

  return (bases || []).map((item) => ({
    id: item.id,
    user_id: item.user_id,
    origin: "cloud" as const,
    name: item.name,
    description: item.description || "",
    color: item.color || "#ff6d29",
    tags: tagMap.get(item.id) || [],
    content_md: item.content_md || "",
    created_at: item.created_at,
    updated_at: item.updated_at,
  }));
}

function cloudKnowledgeBasePayload(kb: KnowledgeBase, userId: string) {
  return {
    id: kb.id,
    user_id: userId,
    name: kb.name,
    description: kb.description,
    color: kb.color,
    content_md: kb.content_md,
    updated_at: new Date().toISOString(),
  };
}

export async function createCloudKnowledgeBase(kb: KnowledgeBase, userId: string): Promise<void> {
  const client = assertClient();
  let createdNow = true;
  const { error } = await client.from("knowledge_bases").insert(cloudKnowledgeBasePayload(kb, userId));
  if (error) {
    if (error.code !== "23505") throw error;
    createdNow = false;

    const { data: existing, error: readError } = await client
      .from("knowledge_bases")
      .select("id")
      .eq("id", kb.id)
      .eq("user_id", userId)
      .maybeSingle();
    if (readError || !existing) throw error;
  }

  try {
    await replaceCloudTags(kb.id, userId, kb.tags || []);
  } catch (tagError) {
    if (createdNow) {
      await client.from("knowledge_bases").delete().eq("id", kb.id).eq("user_id", userId);
    }
    throw tagError;
  }
}

export async function updateCloudKnowledgeBase(kb: KnowledgeBase, userId: string): Promise<void> {
  const client = assertClient();
  const changes = {
    name: kb.name,
    description: kb.description,
    color: kb.color,
    content_md: kb.content_md,
    updated_at: new Date().toISOString(),
  };
  const { data, error } = await client
    .from("knowledge_bases")
    .update(changes)
    .eq("id", kb.id)
    .eq("user_id", userId)
    .select("id");
  if (error) throw error;
  if (!data?.length) {
    throw new Error("该知识库已在其他设备删除，请刷新列表。未重新创建旧数据。");
  }
  await replaceCloudTags(kb.id, userId, kb.tags || []);
}

export async function deleteCloudKnowledgeBase(id: string, userId: string): Promise<void> {
  const client = assertClient();
  const { error } = await client
    .from("knowledge_bases")
    .delete()
    .eq("id", id)
    .eq("user_id", userId);
  if (error) throw error;
}

export async function uploadCloudAttachment(
  knowledgeBaseId: string,
  userId: string,
  file: File,
): Promise<string> {
  const client = assertClient();
  const safeName = file.name.replace(/[^\w.\-\u4e00-\u9fa5]/g, "_");
  const storagePath = `${userId}/${knowledgeBaseId}/${crypto.randomUUID()}-${safeName}`;
  const { error: uploadError } = await client.storage
    .from("knowledge-bar-assets")
    .upload(storagePath, file, { upsert: false });
  if (uploadError) throw uploadError;

  const { error: metadataError } = await client.from("attachments").insert({
    user_id: userId,
    knowledge_base_id: knowledgeBaseId,
    storage_path: storagePath,
    file_name: file.name,
    mime_type: file.type || "application/octet-stream",
    file_size: file.size,
  });
  if (metadataError) throw metadataError;

  return `supabase-storage://knowledge-bar-assets/${storagePath}`;
}

async function replaceCloudTags(
  knowledgeBaseId: string,
  userId: string,
  tags: string[],
): Promise<void> {
  const client = assertClient();
  const cleanTags = Array.from(new Set(tags.map((tag) => tag.trim()).filter(Boolean)));
  const { error: deleteError } = await client
    .from("knowledge_base_tags")
    .delete()
    .eq("knowledge_base_id", knowledgeBaseId);
  if (deleteError) throw deleteError;

  for (const name of cleanTags) {
    const { data: tag, error: tagError } = await client
      .from("tags")
      .upsert({ user_id: userId, name, updated_at: new Date().toISOString() }, { onConflict: "user_id,name" })
      .select("id")
      .single();
    if (tagError) throw tagError;

    const { error: relationError } = await client.from("knowledge_base_tags").insert({
      user_id: userId,
      knowledge_base_id: knowledgeBaseId,
      tag_id: tag.id,
      selected_text: name,
    });
    if (relationError) throw relationError;
  }
}
