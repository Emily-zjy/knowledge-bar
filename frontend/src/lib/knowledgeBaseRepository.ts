import type { KnowledgeBase } from "../types";

export type KnowledgeBaseScope =
  | { mode: "guest" }
  | { mode: "authenticated"; userId: string };

export type KnowledgeBaseRepositories = {
  listGuest: () => Promise<KnowledgeBase[]>;
  listCloud: (userId: string) => Promise<KnowledgeBase[]>;
  saveGuest: (kb: KnowledgeBase) => Promise<void>;
  deleteGuest: (id: string) => Promise<void>;
  createCloud: (kb: KnowledgeBase, userId: string) => Promise<void>;
  updateCloud: (kb: KnowledgeBase, userId: string) => Promise<void>;
  deleteCloud: (id: string, userId: string) => Promise<void>;
};

export function knowledgeBaseScope(userId: string | null | undefined): KnowledgeBaseScope {
  return userId ? { mode: "authenticated", userId } : { mode: "guest" };
}

export function selectionStorageKey(scope: KnowledgeBaseScope): string {
  return scope.mode === "authenticated"
    ? `kb_current_id:authenticated:${scope.userId}`
    : "kb_current_id:guest";
}

export function shouldReturnToDashboardAfterLoad(
  currentPage: string,
  savedCurrentId: string | null,
  items: KnowledgeBase[],
): boolean {
  return currentPage === "detail" && (
    !savedCurrentId || !items.some((item) => item.id === savedCurrentId)
  );
}

function assertOrigin(scope: KnowledgeBaseScope, kb: KnowledgeBase): void {
  const expectedOrigin = scope.mode === "authenticated" ? "cloud" : "guest";
  if (kb.origin !== expectedOrigin) {
    throw new Error("本地草稿与账号数据已隔离，请刷新后重试。");
  }
}

export async function listKnowledgeBases(
  scope: KnowledgeBaseScope,
  repositories: KnowledgeBaseRepositories,
): Promise<KnowledgeBase[]> {
  return scope.mode === "authenticated"
    ? repositories.listCloud(scope.userId)
    : repositories.listGuest();
}

export async function createKnowledgeBaseRecord(
  scope: KnowledgeBaseScope,
  kb: KnowledgeBase,
  repositories: KnowledgeBaseRepositories,
): Promise<void> {
  assertOrigin(scope, kb);
  if (scope.mode === "authenticated") {
    await repositories.createCloud(kb, scope.userId);
    return;
  }
  await repositories.saveGuest(kb);
}

export async function updateKnowledgeBaseRecord(
  scope: KnowledgeBaseScope,
  kb: KnowledgeBase,
  repositories: KnowledgeBaseRepositories,
): Promise<void> {
  assertOrigin(scope, kb);
  if (scope.mode === "authenticated") {
    await repositories.updateCloud(kb, scope.userId);
    return;
  }
  await repositories.saveGuest(kb);
}

export async function deleteKnowledgeBaseRecord(
  scope: KnowledgeBaseScope,
  id: string,
  repositories: KnowledgeBaseRepositories,
): Promise<{ staleLocalCacheDiscarded: boolean; localCleanupFailed: boolean }> {
  if (scope.mode === "guest") {
    await repositories.deleteGuest(id);
    return { staleLocalCacheDiscarded: true, localCleanupFailed: false };
  }

  await repositories.deleteCloud(id, scope.userId);
  try {
    await repositories.deleteGuest(id);
    return { staleLocalCacheDiscarded: true, localCleanupFailed: false };
  } catch {
    return { staleLocalCacheDiscarded: false, localCleanupFailed: true };
  }
}
