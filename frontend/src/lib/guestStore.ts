import type { KnowledgeBase, MindMapData } from "../types";

const dbName = "knowledge-bar-guest";
const kbStore = "guest_knowledge_bases";
const mindMapStore = "guest_mind_maps";

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(dbName, 1);

    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(kbStore)) {
        db.createObjectStore(kbStore, { keyPath: "id" });
      }
      if (!db.objectStoreNames.contains(mindMapStore)) {
        db.createObjectStore(mindMapStore, { keyPath: "knowledge_base_id" });
      }
    };

    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

export async function listGuestKnowledgeBases(): Promise<KnowledgeBase[]> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(kbStore, "readonly");
    const request = tx.objectStore(kbStore).getAll();
    request.onsuccess = () => resolve(
      (request.result as KnowledgeBase[]).map((item) => ({ ...item, origin: "guest" })),
    );
    request.onerror = () => reject(request.error);
  });
}

export async function saveGuestKnowledgeBase(kb: KnowledgeBase): Promise<void> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(kbStore, "readwrite");
    tx.objectStore(kbStore).put({ ...kb, origin: "guest", user_id: undefined });
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

export async function deleteGuestKnowledgeBase(id: string): Promise<void> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction([kbStore, mindMapStore], "readwrite");
    tx.objectStore(kbStore).delete(id);
    tx.objectStore(mindMapStore).delete(id);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

export async function saveGuestMindMap(
  knowledgeBaseId: string,
  mindMap: MindMapData,
): Promise<void> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(mindMapStore, "readwrite");
    tx.objectStore(mindMapStore).put({
      knowledge_base_id: knowledgeBaseId,
      mind_map: mindMap,
      updated_at: new Date().toISOString(),
    });
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

export async function getGuestMindMap(
  knowledgeBaseId: string,
): Promise<MindMapData | null> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(mindMapStore, "readonly");
    const request = tx.objectStore(mindMapStore).get(knowledgeBaseId);
    request.onsuccess = () => resolve(request.result?.mind_map || null);
    request.onerror = () => reject(request.error);
  });
}
