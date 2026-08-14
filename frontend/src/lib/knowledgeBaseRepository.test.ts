import { describe, expect, it, vi } from "vitest";
import type { KnowledgeBase } from "../types";
import {
  createKnowledgeBaseRecord,
  deleteKnowledgeBaseRecord,
  knowledgeBaseScope,
  listKnowledgeBases,
  selectionStorageKey,
  updateKnowledgeBaseRecord,
  type KnowledgeBaseRepositories,
} from "./knowledgeBaseRepository";

function kb(id: string, name: string, origin: KnowledgeBase["origin"]): KnowledgeBase {
  return {
    id,
    origin,
    name,
    description: "",
    color: "#ff6d29",
    tags: [],
    content_md: "",
    created_at: "2026-08-14T00:00:00Z",
    updated_at: "2026-08-14T00:00:00Z",
  };
}

function repositories(overrides: Partial<KnowledgeBaseRepositories> = {}): KnowledgeBaseRepositories {
  return {
    listGuest: vi.fn(async () => []),
    listCloud: vi.fn(async () => []),
    saveGuest: vi.fn(async () => undefined),
    deleteGuest: vi.fn(async () => undefined),
    createCloud: vi.fn(async () => undefined),
    updateCloud: vi.fn(async () => undefined),
    deleteCloud: vi.fn(async () => undefined),
    ...overrides,
  };
}

describe("local/cloud source-of-truth policy", () => {
  it("keeps guest drafts in the guest repository across reload", async () => {
    const draft = kb("guest-1", "GuestDraft1", "guest");
    const repos = repositories({ listGuest: vi.fn(async () => [draft]) });
    const scope = knowledgeBaseScope(null);

    await createKnowledgeBaseRecord(scope, draft, repos);
    const reloaded = await listKnowledgeBases(scope, repos);

    expect(repos.saveGuest).toHaveBeenCalledTimes(1);
    expect(repos.createCloud).not.toHaveBeenCalled();
    expect(reloaded).toEqual([draft]);
  });

  it("does not upload legacy local 122 drafts when an account logs in", async () => {
    const localDrafts = [1, 2, 3].map((index) => kb(`guest-${index}`, "122", "guest"));
    const repos = repositories({
      listGuest: vi.fn(async () => localDrafts),
      listCloud: vi.fn(async () => []),
    });

    const cloudItems = await listKnowledgeBases(knowledgeBaseScope("user-1"), repos);

    expect(cloudItems).toEqual([]);
    expect(repos.listCloud).toHaveBeenCalledWith("user-1");
    expect(repos.listGuest).not.toHaveBeenCalled();
    expect(repos.createCloud).not.toHaveBeenCalled();
  });

  it("never recreates a missing cloud row through the update path", async () => {
    const cloudKb = kb("cloud-1", "122", "cloud");
    const repos = repositories();

    await updateKnowledgeBaseRecord(knowledgeBaseScope("user-1"), cloudKb, repos);

    expect(repos.updateCloud).toHaveBeenCalledTimes(1);
    expect(repos.createCloud).not.toHaveBeenCalled();
    expect(repos.saveGuest).not.toHaveBeenCalled();
  });

  it("deletes cloud data before clearing an equal-id legacy guest shadow", async () => {
    const callOrder: string[] = [];
    const repos = repositories({
      deleteCloud: vi.fn(async () => { callOrder.push("cloud"); }),
      deleteGuest: vi.fn(async () => { callOrder.push("guest-shadow"); }),
    });

    const result = await deleteKnowledgeBaseRecord(knowledgeBaseScope("user-1"), "cloud-1", repos);

    expect(callOrder).toEqual(["cloud", "guest-shadow"]);
    expect(result).toEqual({ staleLocalCacheDiscarded: true, localCleanupFailed: false });
  });

  it("isolates current selections by guest and authenticated user", () => {
    expect(selectionStorageKey(knowledgeBaseScope(null))).toBe("kb_current_id:guest");
    expect(selectionStorageKey(knowledgeBaseScope("user-a"))).toBe("kb_current_id:authenticated:user-a");
    expect(selectionStorageKey(knowledgeBaseScope("user-b"))).toBe("kb_current_id:authenticated:user-b");
  });
});
