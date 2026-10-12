import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type ClipboardEvent,
  type KeyboardEvent,
  type MouseEvent,
} from "react";
import { Routes, Route, useNavigate, useParams, useLocation } from "react-router-dom";
import type { Session } from "@supabase/supabase-js";
import { exportWordDocument } from "./lib/api";
import {
  createCloudKnowledgeBase,
  deleteCloudKnowledgeBase,
  getCloudSession,
  listCloudKnowledgeBases,
  signInWithEmail,
  signOutCloud,
  signUpWithEmail,
  updateCloudKnowledgeBase,
  uploadCloudAttachment,
} from "./lib/cloudStore";
import {
  deleteGuestKnowledgeBase,
  listGuestKnowledgeBases,
  saveGuestKnowledgeBase,
} from "./lib/guestStore";
import {
  createKnowledgeBaseRecord,
  deleteKnowledgeBaseRecord,
  knowledgeBaseScope,
  listKnowledgeBases,
  selectionStorageKey,
  shouldReturnToDashboardAfterLoad,
  updateKnowledgeBaseRecord,
  type KnowledgeBaseRepositories,
} from "./lib/knowledgeBaseRepository";
import { hasSupabaseConfig, supabase } from "./lib/supabase";
import { setAnalyticsToken, trackEvent } from "./lib/analytics";
import MindMapPage from "./pages/MindMapPage";
import FloatingLines from "./components/FloatingLines";
import GlareHover from "./components/GlareHover";
import RotatingText from "./components/RotatingText";
import SplitText from "./components/SplitText";
import "./styles/mindmap.css";
import "./styles/mobile.css";
import type { KnowledgeBase } from "./types";

type PageId = "login" | "register" | "create" | "dashboard" | "settings" | "detail" | "mindmap";
type WorkspacePageId = Exclude<PageId, "login" | "register" | "mindmap">;
type MindMapOrigin = "dashboard" | "detail";
type MindMapLocationState = {
  initialText?: string;
  from?: MindMapOrigin;
  knowledgeBaseId?: string;
};
type ImageCaretSide = "before" | "after";
type AppLocationState = {
  page?: WorkspacePageId;
  currentId?: string;
};

const now = () => new Date().toISOString();
const defaultColor = "#ff6d29";
const knowledgeBaseRepositories: KnowledgeBaseRepositories = {
  listGuest: listGuestKnowledgeBases,
  listCloud: listCloudKnowledgeBases,
  saveGuest: saveGuestKnowledgeBase,
  deleteGuest: deleteGuestKnowledgeBase,
  createCloud: createCloudKnowledgeBase,
  updateCloud: updateCloudKnowledgeBase,
  deleteCloud: deleteCloudKnowledgeBase,
};

function translateAuthError(msg: string): string {
  if (!msg) return "操作失败，请稍后重试。";
  const lower = msg.toLowerCase();
  if (lower.includes("invalid login credentials") || lower.includes("invalid_credentials"))
    return "邮箱或密码不正确。";
  if (lower.includes("email not confirmed"))
    return "邮箱尚未确认，请检查收件箱。";
  if (lower.includes("user already registered") || lower.includes("already been registered"))
    return "该邮箱已注册，请直接登录。";
  if (lower.includes("password") && lower.includes("short"))
    return "密码太短，至少需要6个字符。";
  if (lower.includes("rate limit") || lower.includes("too many"))
    return "请求过于频繁，请稍后再试。";
  if (lower.includes("network") || lower.includes("fetch"))
    return "网络异常，请重试。";
  if (lower.includes("signup") && lower.includes("disabled"))
    return "当前未开放注册，请联系管理员。";
  return msg;
}


const imageMarkdownPattern = /!\[([^\]]*)\]\(([^)]+)\)(?:\{width=(\d+)\})?/g;

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function textToEditorHtml(value: string): string {
  return escapeHtml(value).replace(/\n/g, "<br>");
}

function markdownToEditorHtml(markdown: string): string {
  let html = "";
  let lastIndex = 0;
  for (const match of markdown.matchAll(imageMarkdownPattern)) {
    const [token, alt = "", src = "", width = ""] = match;
    const index = match.index ?? 0;
    html += textToEditorHtml(markdown.slice(lastIndex, index));
    const widthAttr = width ? ` data-width="${escapeHtml(width)}" style="width: ${escapeHtml(width)}px"` : "";
    html += `<figure class="doc-image-block" contenteditable="false" tabindex="0"${widthAttr}><div class="doc-image-toolbar" contenteditable="false"><button type="button" class="doc-image-tool doc-image-delete" data-image-action="delete" aria-label="删除图片">×</button></div><img src="${escapeHtml(src)}" alt="${escapeHtml(
      alt,
    )}" /><figcaption>${escapeHtml(alt || "image")}</figcaption></figure>`;
    lastIndex = index + token.length;
  }
  html += textToEditorHtml(markdown.slice(lastIndex));
  return html;
}

function textToWordHtml(value: string): string {
  return value
    .split(/\r?\n/)
    .map((rawLine) => {
      const line = rawLine.trimEnd();
      if (!line.trim()) return "";
      if (line.startsWith("## ")) return `<h2>${escapeHtml(line.slice(3).trim())}</h2>`;
      if (line.startsWith("# ")) return `<h1>${escapeHtml(line.slice(2).trim())}</h1>`;
      if (line.trimStart().startsWith("- ")) {
        return `<p style="margin: 0 0 8px 24px;">&bull; ${escapeHtml(line.trimStart().slice(2).trim())}</p>`;
      }
      return `<p>${escapeHtml(line)}</p>`;
    })
    .join("");
}

function markdownToWordHtml(markdown: string): string {
  let html = "";
  let lastIndex = 0;

  for (const match of markdown.matchAll(imageMarkdownPattern)) {
    const [token, alt = "", src = "", width = ""] = match;
    const index = match.index ?? 0;
    html += textToWordHtml(markdown.slice(lastIndex, index));

    const widthValue = Number(width);
    const widthStyle = Number.isFinite(widthValue) && widthValue > 0
      ? `width: ${Math.min(widthValue, 640)}px;`
      : "max-width: 640px;";
    html += `<figure style="margin: 18px 0;"><img src="${escapeHtml(src)}" alt="${escapeHtml(
      alt || "image",
    )}" style="${widthStyle} height: auto; display: block;" /><figcaption style="color: #77716c; font-size: 12px; margin-top: 6px;">${escapeHtml(
      alt || "image",
    )}</figcaption></figure>`;

    lastIndex = index + token.length;
  }

  html += textToWordHtml(markdown.slice(lastIndex));
  return html;
}

function editorElementToMarkdown(root: HTMLElement): string {
  function walk(node: globalThis.Node): string {
    if (node.nodeType === globalThis.Node.TEXT_NODE) return node.textContent || "";
    if (!(node instanceof HTMLElement)) return "";

    if (node.tagName === "BR") return "\n";

    if (node.tagName === "IMG") {
      const alt = node.getAttribute("alt") || "image";
      const src = node.getAttribute("src") || "";
      return src ? `![${alt}](${src})` : "";
    }

    if (node.tagName === "FIGURE") {
      const image = node.querySelector("img");
      if (!image) return "";
      const alt = image.getAttribute("alt") || "image";
      const src = image.getAttribute("src") || "";
      const width = Math.round(node.getBoundingClientRect().width || Number(node.dataset.width) || 0);
      const widthToken = width > 0 ? `{width=${width}}` : "";
      return src ? `\n\n![${alt}](${src})${widthToken}\n\n` : "";
    }

    const content = Array.from(node.childNodes).map(walk).join("");
    if (["DIV", "P", "LI"].includes(node.tagName)) return `${content}\n`;
    return content;
  }

  return Array.from(root.childNodes)
    .map(walk)
    .join("")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{8,}/g, "\n\n\n\n\n\n\n")
    .trimEnd();
}

function sanitizeImageName(name: string): string {
  return name.split("[").join(" ").split("]").join(" ").replace(/[\r\n]/g, " ").trim() || "image";
}

function splitTags(value: string): string[] {
  return value
    .split(/[，,、\s]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function createKnowledgeBase(input: {
  id: string;
  origin: KnowledgeBase["origin"];
  name: string;
  description: string;
  tags: string;
}): KnowledgeBase {
  const timestamp = now();
  return {
    id: input.id,
    origin: input.origin,
    name: input.name,
    description: input.description,
    color: defaultColor,
    tags: splitTags(input.tags),
    content_md: "",
    created_at: timestamp,
    updated_at: timestamp,
  };
}


function downloadTextFile(filename: string, content: string, type: string) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.style.display = "none";
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function MindMapRoute() {
  const { taskId } = useParams<{ taskId: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const routeState = (location.state as MindMapLocationState | null) ?? {};
  const initialText = routeState.initialText;
  const handleBack = () => {
    if (routeState.from === "detail") {
      sessionStorage.setItem("kb_page", "detail");
      navigate("/", {
        replace: true,
        state: { page: "detail", currentId: routeState.knowledgeBaseId } satisfies AppLocationState,
      });
      return;
    }

    if (routeState.from === "dashboard") {
      sessionStorage.setItem("kb_page", "dashboard");
      navigate("/", { replace: true, state: { page: "dashboard" } satisfies AppLocationState });
      return;
    }

    if (window.history.length > 1) {
      navigate(-1);
    } else {
      navigate("/", { replace: true, state: { page: "dashboard" } satisfies AppLocationState });
    }
  };
  return (
    <div className="shell shell--fullscreen app-theme">
      <header className="global-header">
        <button type="button" className="brand reset-button" onClick={() => navigate("/")}>
          <div className="brand-mark">
            <img src="/knowledge-bar-logo.png" alt="Knowledge Bar logo" />
          </div>
          <div>
            <div className="brand-title">Knowledge Bar</div>
            <div className="brand-subtitle">AI knowledge base and mind map studio</div>
          </div>
        </button>
      </header>
      <main>
        <MindMapPage
          onBack={handleBack}
          initialText={initialText}
          returnState={routeState}
          taskId={taskId === "new" ? undefined : taskId}
        />
      </main>
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/mindmap/:taskId" element={<MindMapRoute />} />
      <Route path="*" element={<AppShell />} />
    </Routes>
  );
}

function AppShell() {
  const navigate = useNavigate();
  const location = useLocation();
  const [page, setPage] = useState<PageId>(() => {
    const saved = sessionStorage.getItem("kb_page") as PageId | null;
    return saved && saved !== "login" && saved !== "register" ? saved : "login";
  });
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [currentId, setCurrentId] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [query, setQuery] = useState("");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [mobileEditorMenuOpen, setMobileEditorMenuOpen] = useState(false);
  const [guestDraftContent, setGuestDraftContent] = useState("");
  const [guestDraftTags, setGuestDraftTags] = useState<string[]>([]);
  const [selectedDocText, setSelectedDocText] = useState("");
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [session, setSession] = useState<Session | null>(null);
  const docEditorRef = useRef<HTMLDivElement | null>(null);
  const imageInputRef = useRef<HTMLInputElement | null>(null);
  const lastEditorContentRef = useRef("");
  const imageCaretRef = useRef<{ figure: HTMLElement; side: ImageCaretSide } | null>(null);
  const avatarInputRef = useRef<HTMLInputElement | null>(null);
  const [avatarUrl, setAvatarUrl] = useState<string | null>(null);
  const [loginForm, setLoginForm] = useState({
    email: "",
    password: "",
  });
  const [registerForm, setRegisterForm] = useState({
    email: "",
    password: "",
  });
  const [createForm, setCreateForm] = useState({
    name: "",
    description: "",
    tags: "",
  });
  const [isCreating, setIsCreating] = useState(false);
  const createIntentIdRef = useRef<string | null>(null);
  const pendingCreateRef = useRef<{ fingerprint: string; id: string } | null>(null);
  const deleteIntentIdRef = useRef<string | null>(null);
  const knowledgeBaseLoadEpochRef = useRef(0);

  useEffect(() => {
    void bootstrapSession();
  }, []);

  useEffect(() => {
    const navState = location.state as AppLocationState | null;
    if (!navState?.page) return;

    setPage(navState.page);
    sessionStorage.setItem("kb_page", navState.page);
    if (navState.currentId) {
      setCurrentId(navState.currentId);
    }
  }, [location.state]);

  async function bootstrapSession() {
    let savedSession: Session | null = null;
    try {
      savedSession = await getCloudSession();
    } catch (error) {
      setSession(null);
      setAnalyticsToken(null);
      setMessage(error instanceof Error ? error.message : "云端会话读取失败，已进入游客模式。");
      await refreshKnowledgeBases(null);
      return;
    }

    setSession(savedSession);
    setAnalyticsToken(savedSession?.access_token || null);
    if (!savedSession) {
      await refreshKnowledgeBases(null);
      return;
    }

    setKnowledgeBases([]);
    setCurrentId(null);
    try {
      await refreshKnowledgeBases(savedSession.user.id);
      void loadAvatar(savedSession.user.id);
    } catch (error) {
      setKnowledgeBases([]);
      setCurrentId(null);
      setMessage(error instanceof Error ? error.message : "云端知识库读取失败，请重试。");
    }
  }

  async function refreshKnowledgeBases(targetUserId: string | null) {
    const loadEpoch = ++knowledgeBaseLoadEpochRef.current;
    const scope = knowledgeBaseScope(hasSupabaseConfig ? targetUserId : null);
    const items = await listKnowledgeBases(scope, knowledgeBaseRepositories);
    if (loadEpoch !== knowledgeBaseLoadEpochRef.current) return;

    setKnowledgeBases(items);
    const storageKey = selectionStorageKey(scope);
    const savedCurrentId = sessionStorage.getItem(storageKey);
    if (shouldReturnToDashboardAfterLoad(page, savedCurrentId, items)) {
      setPage("dashboard");
      sessionStorage.setItem("kb_page", "dashboard");
    }
    const nextCurrentId = items.find((item) => item.id === savedCurrentId)?.id ?? items[0]?.id ?? null;
    setCurrentId(nextCurrentId);
    if (nextCurrentId) {
      sessionStorage.setItem(storageKey, nextCurrentId);
    } else {
      sessionStorage.removeItem(storageKey);
    }
  }

  function showPage(next: PageId) {
    setMessage("");
    setMobileSidebarOpen(false);
    setMobileEditorMenuOpen(false);
    setPage(next);
    sessionStorage.setItem("kb_page", next);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  const currentKb = useMemo(
    () => knowledgeBases.find((item) => item.id === currentId) || knowledgeBases[0] || null,
    [currentId, knowledgeBases],
  );

  const filteredKnowledgeBases = knowledgeBases.filter((item) => {
    const target = `${item.name} ${item.description}`.toLowerCase();
    return target.includes(query.toLowerCase());
  });

  const docContent = currentKb?.content_md ?? guestDraftContent;
  const currentTags = currentKb?.tags ?? guestDraftTags;
  const activeUserId = session?.user.id || null;
  const isCloudMode = Boolean(hasSupabaseConfig && activeUserId);
  const uniqueTags = useMemo(
    () => Array.from(new Set(knowledgeBases.flatMap((item) => item.tags || []))),
    [knowledgeBases],
  );
  const latestUpdatedAt = useMemo(() => {
    const timestamps = knowledgeBases
      .map((item) => item.updated_at)
      .filter(Boolean)
      .sort((a, b) => new Date(b).getTime() - new Date(a).getTime());
    return timestamps[0] || "";
  }, [knowledgeBases]);
  const filledDocCount = useMemo(
    () => knowledgeBases.filter((item) => item.content_md.trim().length > 0).length,
    [knowledgeBases],
  );

  function formatDateLabel(value?: string) {
    if (!value) return "暂无更新";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "暂无更新";
    return date.toLocaleDateString("zh-CN", { month: "2-digit", day: "2-digit" });
  }

  useEffect(() => {
    if (page !== "detail") return;
    const editor = docEditorRef.current;
    if (!editor) return;
    if (lastEditorContentRef.current === docContent && editor.innerHTML) return;
    editor.innerHTML = markdownToEditorHtml(docContent);
    lastEditorContentRef.current = docContent;
  }, [currentId, docContent, page]);

  async function persistKnowledgeBase(kb: KnowledgeBase) {
    await updateKnowledgeBaseRecord(
      knowledgeBaseScope(isCloudMode ? activeUserId : null),
      kb,
      knowledgeBaseRepositories,
    );
  }

  async function handlePersistenceFailure(error: unknown) {
    const errorMessage = error instanceof Error ? error.message : "保存失败，请重试。";
    setMessage(errorMessage);
    if (!isCloudMode || !activeUserId || !errorMessage.includes("已在其他设备删除")) return;

    const scope = knowledgeBaseScope(activeUserId);
    setCurrentId(null);
    sessionStorage.removeItem(selectionStorageKey(scope));
    try {
      await refreshKnowledgeBases(activeUserId);
      showPage("dashboard");
    } catch {
      setKnowledgeBases([]);
    }
  }

  async function renameCurrentKnowledgeBase() {
    if (!currentKb) return;
    const newName = window.prompt("重命名知识库", currentKb.name);
    if (!newName || !newName.trim() || newName.trim() === currentKb.name) return;
    const updated = { ...currentKb, name: newName.trim(), updated_at: now() };
    try {
      await persistKnowledgeBase(updated);
      setKnowledgeBases((items) => items.map((item) => (item.id === updated.id ? updated : item)));
      setMessage("已重命名");
    } catch (error) {
      await handlePersistenceFailure(error);
    }
  }

  async function loadAvatar(userId: string) {
    if (!supabase) return;
    const { data } = await supabase.from("profiles").select("avatar_path").eq("id", userId).single();
    if (!data?.avatar_path) return;
    const { data: signed } = await supabase.storage
      .from("knowledge-bar-assets")
      .createSignedUrl(data.avatar_path, 3600);
    if (signed?.signedUrl) setAvatarUrl(signed.signedUrl);
  }

  async function handleAvatarUpload(file: File) {
    if (!supabase || !activeUserId) return;
    const ext = file.name.split(".").pop() || "png";
    const storagePath = `${activeUserId}/avatar/avatar.${ext}`;
    const { error: uploadErr } = await supabase.storage
      .from("knowledge-bar-assets")
      .upload(storagePath, file, { upsert: true });
    if (uploadErr) { setMessage("头像上传失败：" + uploadErr.message); return; }
    const { error: profileErr } = await supabase
      .from("profiles")
      .upsert({ id: activeUserId, avatar_path: storagePath, updated_at: new Date().toISOString() }, { onConflict: "id" });
    if (profileErr) { setMessage("保存头像路径失败：" + profileErr.message); return; }
    const { data: signed } = await supabase.storage
      .from("knowledge-bar-assets")
      .createSignedUrl(storagePath, 3600);
    if (signed?.signedUrl) setAvatarUrl(signed.signedUrl);
    setMessage("头像已更新");
  }


  async function handleLogin() {
    if (!/^\S+@\S+\.\S+$/.test(loginForm.email.trim())) {
      setMessage("请输入正确邮箱。");
      return;
    }
    if (!hasSupabaseConfig) {
      setMessage("当前未配置 Supabase，已使用游客模式体验。");
      showPage("dashboard");
      return;
    }
    try {
      const nextSession = await signInWithEmail(loginForm.email.trim(), loginForm.password);
      setKnowledgeBases([]);
      setCurrentId(null);
      setSession(nextSession);
      setAnalyticsToken(nextSession.access_token);
      await refreshKnowledgeBases(nextSession.user.id);
      showPage("dashboard");
    } catch (error) {
      const raw = error instanceof Error ? error.message : "";
      setMessage(translateAuthError(raw));
    }
  }

  async function handleRegister() {
    if (!/^\S+@\S+\.\S+$/.test(registerForm.email.trim())) {
      setMessage("请输入正确邮箱。");
      return;
    }
    if (registerForm.password.length < 6) {
      setMessage("密码至少需要6个字符。");
      return;
    }
    if (!hasSupabaseConfig) {
      setMessage("当前未配置 Supabase，暂时只能游客体验。");
      return;
    }
    try {
      const nextSession = await signUpWithEmail(registerForm.email.trim(), registerForm.password);
      if (!nextSession) {
        setMessage("账号已创建，但当前 Supabase 项目仍要求邮箱确认。请检查邮箱后登录。");
        setPage("login");
        window.scrollTo({ top: 0, behavior: "smooth" });
        return;
      }
      setKnowledgeBases([]);
      setCurrentId(null);
      setSession(nextSession);
      setAnalyticsToken(nextSession.access_token);
      await refreshKnowledgeBases(nextSession.user.id);
      showPage("dashboard");
    } catch (error) {
      const raw = error instanceof Error ? error.message : "";
      setMessage(translateAuthError(raw));
    }
  }

  async function handleSignOut() {
    try {
      ++knowledgeBaseLoadEpochRef.current;
      await signOutCloud();
      setSession(null);
      setAnalyticsToken(null);
      setKnowledgeBases([]);
      setCurrentId(null);
      await refreshKnowledgeBases(null);
      showPage("login");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "退出登录失败，请重试。");
    }
  }

  async function submitCreate() {
    if (createIntentIdRef.current) return;
    if (!createForm.name.trim()) {
      setMessage("请输入 bar 名称。");
      return;
    }
    createIntentIdRef.current = crypto.randomUUID();
    setIsCreating(true);
    setMessage("");
    const intentId = createIntentIdRef.current;
    const scope = knowledgeBaseScope(isCloudMode ? activeUserId : null);
    const fingerprint = JSON.stringify({
      mode: scope.mode,
      userId: scope.mode === "authenticated" ? scope.userId : null,
      name: createForm.name.trim(),
      description: createForm.description.trim(),
      tags: splitTags(createForm.tags),
    });
    if (!pendingCreateRef.current || pendingCreateRef.current.fingerprint !== fingerprint) {
      pendingCreateRef.current = { fingerprint, id: crypto.randomUUID() };
    }
    const kb = createKnowledgeBase({
      id: pendingCreateRef.current.id,
      origin: scope.mode === "authenticated" ? "cloud" : "guest",
      name: createForm.name.trim(),
      description: createForm.description.trim(),
      tags: createForm.tags,
    });
    trackEvent({
      event_name: "knowledge_base_create_clicked",
      properties: { mode: scope.mode, name_length: kb.name.length },
    });
    try {
      await createKnowledgeBaseRecord(scope, kb, knowledgeBaseRepositories);
      if (createIntentIdRef.current !== intentId) return;
      setCurrentId(kb.id);
      sessionStorage.setItem(selectionStorageKey(scope), kb.id);
      setKnowledgeBases((items) => [kb, ...items]);
      setCreateForm({ name: "", description: "", tags: "" });
      pendingCreateRef.current = null;
      trackEvent({
        event_name: "knowledge_base_create_succeeded",
        knowledge_base_id: kb.id,
        properties: { mode: scope.mode },
      });
      showPage("detail");
    } catch (error) {
      if (createIntentIdRef.current !== intentId) return;
      trackEvent({
        event_name: "knowledge_base_create_failed",
        properties: { mode: scope.mode, error_type: error instanceof Error ? error.name : "unknown" },
      });
      setMessage(error instanceof Error ? error.message : "创建失败，请重试。");
    } finally {
      createIntentIdRef.current = null;
      setIsCreating(false);
    }
  }

  async function confirmDeleteKnowledgeBase() {
    const id = deleteConfirmId;
    if (!id || deleteIntentIdRef.current) return;
    deleteIntentIdRef.current = id;
    setIsDeleting(true);
    setMessage("");
    const scope = knowledgeBaseScope(isCloudMode ? activeUserId : null);

    try {
      const result = await deleteKnowledgeBaseRecord(scope, id, knowledgeBaseRepositories);
      setKnowledgeBases((items) => items.filter((kb) => kb.id !== id));
      if (currentId === id) {
        setCurrentId(null);
        sessionStorage.removeItem(selectionStorageKey(scope));
      }
      setDeleteConfirmId(null);
      setMessage(result.localCleanupFailed ? "云端已删除；本地缓存清理失败，但不会重新上传。" : "知识库已删除。");
      if (result.staleLocalCacheDiscarded && scope.mode === "authenticated") {
        trackEvent({
          event_name: "stale_local_cache_discarded",
          knowledge_base_id: id,
          properties: { reason: "cloud_delete" },
        });
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "删除失败，请重试。");
    } finally {
      deleteIntentIdRef.current = null;
      setIsDeleting(false);
    }
  }

  async function saveCurrentContent(content: string) {
    if (!currentKb) {
      setGuestDraftContent(content);
      return;
    }
    const updated = { ...currentKb, content_md: content, updated_at: now() };
    await persistKnowledgeBase(updated);
    setKnowledgeBases((items) => items.map((item) => (item.id === updated.id ? updated : item)));
  }

  async function appendContent(value: string) {
    await saveCurrentContent(`${docContent}${docContent ? "\n\n" : ""}${value}`);
  }

  function readFileAsDataUrl(file: File): Promise<string> {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result));
      reader.onerror = () => reject(reader.error);
      reader.readAsDataURL(file);
    });
  }

  async function addImage(file: File) {
    const imageName = sanitizeImageName(file.name);
    if (isCloudMode && activeUserId && currentKb) {
      const path = await uploadCloudAttachment(currentKb.id, activeUserId, file);
      await appendContent(`![${imageName}](${path})`);
      setMessage("图片已上传并插入到文档。");
      return;
    }

    const dataUrl = await readFileAsDataUrl(file);
    await appendContent(`![${imageName}](${dataUrl})`);
    setMessage("图片已插入到本地草稿。");
  }

  async function handleImageFileInput(file: File | undefined) {
    if (!file) return;
    try {
      await addImage(file);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "图片添加失败，请重试。");
    }
  }

  async function addSelectedTextAsTag() {
    const selected = selectedDocText.trim();
    if (!selected) {
      setMessage("请先在编辑区选中一段文字，再添加标签。");
      return;
    }
    const tag = selected.slice(0, 18);
    const nextTags = Array.from(new Set([...currentTags, tag]));
    try {
      if (currentKb) {
        const updated = { ...currentKb, tags: nextTags, updated_at: now() };
        await persistKnowledgeBase(updated);
        setKnowledgeBases((items) => items.map((item) => (item.id === updated.id ? updated : item)));
      } else {
        setGuestDraftTags(nextTags);
      }
      setMessage("标签已添加到当前知识库。");
    } catch (error) {
      await handlePersistenceFailure(error);
    }
  }


  async function handleEditorPaste(event: ClipboardEvent<HTMLDivElement>) {
    const imageFile = Array.from(event.clipboardData.files).find((file) => file.type.startsWith("image/"));
    if (!imageFile) return;
    event.preventDefault();
    try {
      await addImage(imageFile);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Image paste failed.");
    }
  }

  function handleEditorInput() {
    const editor = docEditorRef.current;
    if (!editor) return;
    const nextContent = editorElementToMarkdown(editor);
    lastEditorContentRef.current = nextContent;
    void saveCurrentContent(nextContent).catch((error) => void handlePersistenceFailure(error));
  }

  function getImageFigure(target: EventTarget | null) {
    if (!(target instanceof HTMLElement)) return null;
    return target.closest<HTMLElement>(".doc-image-block");
  }

  function getImageAction(target: EventTarget | null) {
    if (!(target instanceof HTMLElement)) return null;
    return target.closest<HTMLElement>("[data-image-action]")?.dataset.imageAction || null;
  }

  function syncImageFigureSize(figure: HTMLElement) {
    const width = Math.round(figure.getBoundingClientRect().width);
    if (width > 0) {
      figure.dataset.width = String(width);
      figure.style.width = `${width}px`;
    }
  }

  function clearImageCaretMarker() {
    docEditorRef.current
      ?.querySelectorAll(".doc-image-block.is-caret-before, .doc-image-block.is-caret-after")
      .forEach((item) => item.classList.remove("is-caret-before", "is-caret-after"));
    imageCaretRef.current = null;
  }

  function setImageCaret(figure: HTMLElement, side: ImageCaretSide) {
    const editor = docEditorRef.current;
    if (!editor || !editor.contains(figure)) return;

    clearImageCaretMarker();
    figure.classList.add(side === "before" ? "is-caret-before" : "is-caret-after");
    imageCaretRef.current = { figure, side };

    const range = document.createRange();
    if (side === "before") range.setStartBefore(figure);
    else range.setStartAfter(figure);
    range.collapse(true);
    const selection = window.getSelection();
    selection?.removeAllRanges();
    selection?.addRange(range);
    editor.focus();
  }

  function handleEditorMouseUp(event: MouseEvent<HTMLDivElement>) {
    rememberSelectedText();
    const figure = getImageFigure(event.target);
    if (!figure) return;
    requestAnimationFrame(() => {
      syncImageFigureSize(figure);
      handleEditorInput();
    });
  }

  function handleEditorClick(event: MouseEvent<HTMLDivElement>) {
    const action = getImageAction(event.target);
    const figure = getImageFigure(event.target);
    if (action === "delete") {
      if (!figure) return;
      event.preventDefault();
      event.stopPropagation();
      figure.remove();
      clearImageCaretMarker();
      handleEditorInput();
      setMessage("图片已删除。");
      return;
    }

    if (figure) {
      event.preventDefault();
      event.stopPropagation();
      syncImageFigureSize(figure);
      const box = figure.getBoundingClientRect();
      setImageCaret(figure, event.clientX < box.left + box.width / 2 ? "before" : "after");
      return;
    }

    clearImageCaretMarker();
  }

  function getSelectedImageFigure() {
    const editor = docEditorRef.current;
    const selection = window.getSelection();
    if (!editor || !selection || selection.rangeCount === 0) return null;

    const range = selection.getRangeAt(0);
    const anchor =
      selection.anchorNode instanceof HTMLElement ? selection.anchorNode : selection.anchorNode?.parentElement || null;
    const fromAnchor = anchor?.closest<HTMLElement>(".doc-image-block");
    if (fromAnchor && editor.contains(fromAnchor)) return fromAnchor;

    if (range.startContainer === editor) {
      const before = editor.childNodes[Math.max(0, range.startOffset - 1)];
      const current = editor.childNodes[range.startOffset];
      for (const candidate of [current, before]) {
        if (candidate instanceof HTMLElement && candidate.matches(".doc-image-block")) return candidate;
      }
    }

    return null;
  }

  function getActiveImageCaret() {
    const editor = docEditorRef.current;
    const active = imageCaretRef.current;
    if (active && editor?.contains(active.figure)) return active;
    const figure = getSelectedImageFigure();
    return figure ? { figure, side: "after" as ImageCaretSide } : null;
  }

  function isEmptyEditorLine(node: Element | null | undefined) {
    if (!(node instanceof HTMLElement)) return false;
    if (node.matches(".doc-image-block")) return false;
    return !node.querySelector("img, figure") && !node.textContent?.trim();
  }

  function insertLineAroundImage(figure: HTMLElement, side: ImageCaretSide) {
    const line = document.createElement("div");
    line.append(document.createElement("br"));
    if (side === "before") figure.before(line);
    else figure.after(line);

    setImageCaret(figure, side);
    handleEditorInput();
  }

  function removeAdjacentEmptyLine(figure: HTMLElement, side: ImageCaretSide) {
    const target = side === "before" ? figure.previousElementSibling : figure.nextElementSibling;
    if (!(target instanceof HTMLElement) || !isEmptyEditorLine(target)) return false;
    target.remove();
    setImageCaret(figure, side);
    handleEditorInput();
    return true;
  }

  function getCaretLineElement() {
    const editor = docEditorRef.current;
    const selection = window.getSelection();
    if (!editor || !selection || selection.rangeCount === 0) return null;

    const range = selection.getRangeAt(0);
    let node: globalThis.Node | null = range.startContainer;
    if (node === editor) {
      node = editor.childNodes[range.startOffset] || editor.childNodes[Math.max(0, range.startOffset - 1)] || null;
    }

    let element = node instanceof HTMLElement ? node : node?.parentElement || null;
    while (element && element.parentElement !== editor) element = element.parentElement;
    return element && element !== editor ? element : null;
  }

  function handleEmptyLineDelete(event: KeyboardEvent<HTMLDivElement>) {
    const line = getCaretLineElement();
    if (!isEmptyEditorLine(line)) return false;

    const previous = line?.previousElementSibling;
    const next = line?.nextElementSibling;
    if (event.key === "Backspace" && previous instanceof HTMLElement && previous.matches(".doc-image-block")) {
      line?.remove();
      setImageCaret(previous, "after");
      handleEditorInput();
      return true;
    }
    if (event.key === "Delete" && next instanceof HTMLElement && next.matches(".doc-image-block")) {
      line?.remove();
      setImageCaret(next, "before");
      handleEditorInput();
      return true;
    }
    return false;
  }

  function handleEditorKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Delete" || event.key === "Backspace") {
      const active = getActiveImageCaret();
      if (active && removeAdjacentEmptyLine(active.figure, active.side)) {
        event.preventDefault();
        event.stopPropagation();
        return;
      }
      if (handleEmptyLineDelete(event)) {
        event.preventDefault();
        event.stopPropagation();
      }
      return;
    }

    if (event.key !== "Enter") return;
    const active = getActiveImageCaret();
    if (!active) return;
    event.preventDefault();
    event.stopPropagation();
    syncImageFigureSize(active.figure);
    insertLineAroundImage(active.figure, active.side);
  }

  function getEditorSelectedText() {
    const editor = docEditorRef.current;
    const selection = window.getSelection();
    if (!editor || !selection || selection.rangeCount === 0) return "";
    const anchor = selection.anchorNode;
    const focus = selection.focusNode;
    if ((anchor && editor.contains(anchor)) || (focus && editor.contains(focus))) {
      return selection.toString().trim();
    }
    return "";
  }


  function rememberSelectedText() {
    const selected = getEditorSelectedText();
    if (selected) {
      setSelectedDocText(selected);
    }
  }




  function exportMarkdown() {
    if (!docContent.trim()) {
      setMessage("暂无内容可导出。");
      return;
    }
    downloadTextFile(`${currentKb?.name || "knowledge-bar"}.md`, docContent, "text/markdown;charset=utf-8");
  }

  async function exportWord() {
    const title = currentKb?.name || "Knowledge Bar";
    const source = docContent;
    try {
      const savedSession = await getCloudSession();
      const blob = await exportWordDocument({
        title,
        markdown: source,
        knowledgeBaseId: currentKb?.id,
        token: savedSession?.access_token,
      });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${title}.docx`;
      anchor.style.display = "none";
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      setMessage("已导出 Word 文件。");
    } catch {
      const body = source.trim() ? markdownToWordHtml(source) : "<p>暂无内容</p>";
      const html = `<!doctype html><html><head><meta charset="utf-8"><title>${escapeHtml(
        title,
      )}</title></head><body><h1>${escapeHtml(title)}</h1>${body}</body></html>`;
      downloadTextFile(`${title}.doc`, html, "application/msword;charset=utf-8");
      setMessage("后端暂不可用，已导出 Word 兼容文件。");
    }
  }

  return (
    <div className={`shell ${page === "login" || page === "register" ? "" : "app-theme"} ${page === "detail" ? "shell--editor" : ""}`}>
      <header className="global-header">
        <button type="button" className="brand reset-button" onClick={() => showPage("dashboard")}>
          <div className="brand-mark">
            <img src="/knowledge-bar-logo.png" alt="Knowledge Bar logo" />
          </div>
          <div>
            <div className="brand-title">Knowledge Bar</div>
            <div className="brand-subtitle">AI knowledge base and mind map studio</div>
          </div>
        </button>
        {(page === "dashboard" || page === "settings" || page === "detail") && (
          <button
            type="button"
            className="mobile-menu-toggle"
            aria-label="打开菜单"
            onClick={() => setMobileSidebarOpen((v) => !v)}
          >
            ☰
          </button>
        )}
      </header>

      {mobileSidebarOpen && (
        <div className="mobile-sidebar-backdrop visible" onClick={() => setMobileSidebarOpen(false)} />
      )}

      <main>
        {page === "login" && (
          <section className="page active">
            <div className="surface hero-slab hero-slab--grainient">
              <div className="hero-slab__bg">
                <FloatingLines
                  enabledWaves={['top', 'middle', 'bottom']}
                  lineCount={8}
                  lineDistance={34}
                  bendRadius={8}
                  bendStrength={-2}
                  interactive={true}
                  parallax={true}
                  animationSpeed={1}
                  linesGradient={["#F97316", "#6f6f6f", "#6a6a6a"]}
                  mixBlendMode="normal"
                />
              </div>
              <section className="hero-blue">
                <SplitText
                  tag="h1"
                  text="Knowledge Bar"
                  className=""
                  delay={60}
                  duration={0.8}
                  ease="power3.out"
                  splitType="chars"
                  from={{ opacity: 0, y: 50 }}
                  to={{ opacity: 1, y: 0 }}
                  threshold={0.1}
                  rootMargin="-50px"
                  textAlign="left"
                />
                <SplitText
                  tag="div"
                  text="Open study bar / AI mind map"
                  className="kicker"
                  delay={30}
                  duration={0.6}
                  ease="power3.out"
                  splitType="chars"
                  from={{ opacity: 0, y: 20 }}
                  to={{ opacity: 1, y: 0 }}
                  threshold={0.1}
                  rootMargin="-50px"
                  textAlign="left"
                />
                <SplitText
                  tag="p"
                  text="把零散笔记调成一杯清醒的知识鸡尾酒。输入文字，沉淀资料，让 AI 生成可编辑的思维导图。"
                  className="hero-copy"
                  delay={20}
                  duration={0.5}
                  ease="power2.out"
                  splitType="words"
                  from={{ opacity: 0, y: 30 }}
                  to={{ opacity: 1, y: 0 }}
                  threshold={0.1}
                  rootMargin="-50px"
                  textAlign="left"
                />
              </section>
              <section className="login-panel login-panel--entry">
                <h2 className="panel-title login-panel-title">
                  <span className="login-panel-title__brand">Knowledge Bar</span>
                </h2>
                <p className="panel-desc">使用邮箱和密码登录。</p>
                <div className="field">
                  <label htmlFor="login-email">邮箱</label>
                  <input
                    id="login-email"
                    type="email"
                    value={loginForm.email}
                    placeholder="name@example.com"
                    onChange={(event) => setLoginForm({ ...loginForm, email: event.target.value })}
                  />
                </div>
                <div className="field">
                  <label htmlFor="login-password">密码</label>
                  <input
                    id="login-password"
                    type="password"
                    value={loginForm.password}
                    placeholder="请输入密码"
                    onChange={(event) =>
                      setLoginForm({ ...loginForm, password: event.target.value })
                    }
                    onKeyDown={(event) => { if (event.key === "Enter") void handleLogin(); }}
                  />
                </div>
                {message && <div className="status">{message}</div>}
                <div className="button-row">
                  <button type="button" className="primary" onClick={handleLogin}>
                    登录
                  </button>
                  <button type="button" className="ghost" onClick={() => showPage("dashboard")}>
                    游客体验
                  </button>
                </div>
                <div className="hint-link">
                  <span>还没有账号？</span>
                  <button type="button" onClick={() => showPage("register")}>
                    注册
                  </button>
                </div>
              </section>
            </div>
          </section>
        )}

        {page === "register" && (
          <section className="page active">
            <div className="surface hero-slab hero-slab--grainient">
              <div className="hero-slab__bg">
                <FloatingLines
                  enabledWaves={['top', 'middle', 'bottom']}
                  lineCount={8}
                  lineDistance={34}
                  bendRadius={8}
                  bendStrength={-2}
                  interactive={true}
                  parallax={true}
                  animationSpeed={1}
                  linesGradient={["#F97316", "#ffffff", "#f4f4f5"]}
                  mixBlendMode="screen"
                />
              </div>
              <section className="hero-blue">
                <SplitText
                  tag="h1"
                  text="创建 Knowledge Bar"
                  className="register-title"
                  delay={60}
                  duration={0.8}
                  ease="power3.out"
                  splitType="chars"
                  from={{ opacity: 0, y: 50 }}
                  to={{ opacity: 1, y: 0 }}
                  threshold={0.1}
                  rootMargin="-50px"
                  textAlign="left"
                />
                <SplitText
                  tag="div"
                  text="Create your own bar"
                  className="kicker"
                  delay={30}
                  duration={0.6}
                  ease="power3.out"
                  splitType="chars"
                  from={{ opacity: 0, y: 20 }}
                  to={{ opacity: 1, y: 0 }}
                  threshold={0.1}
                  rootMargin="-50px"
                  textAlign="left"
                />
                <SplitText
                  tag="p"
                  text="只需要邮箱和密码，先开一间自己的知识工作室。后续可以继续补充云端保存、使用次数和会员能力。"
                  className="hero-copy"
                  delay={20}
                  duration={0.5}
                  ease="power2.out"
                  splitType="words"
                  from={{ opacity: 0, y: 30 }}
                  to={{ opacity: 1, y: 0 }}
                  threshold={0.1}
                  rootMargin="-50px"
                  textAlign="left"
                />
              </section>
              <section className="login-panel">
                <GlareHover
                  width="100%"
                  height="auto"
                  background="transparent"
                  borderRadius="14px"
                  borderColor="transparent"
                  glareColor="#ffffff"
                  glareOpacity={0.28}
                  glareAngle={-30}
                  glareSize={300}
                  transitionDuration={800}
                  className="panel-title-glare"
                >
                  <h2 className="panel-title">Knowledge Bar</h2>
                </GlareHover>
                <p className="panel-desc">创建账号</p>
                <div className="field">
                  <label htmlFor="register-email">邮箱</label>
                  <input
                    id="register-email"
                    type="email"
                    value={registerForm.email}
                    placeholder="name@example.com"
                    onChange={(event) =>
                      setRegisterForm({ ...registerForm, email: event.target.value })
                    }
                  />
                </div>
                <div className="field">
                  <label htmlFor="register-password">密码</label>
                  <input
                    id="register-password"
                    type="password"
                    value={registerForm.password}
                    placeholder="设置密码"
                    onChange={(event) =>
                      setRegisterForm({ ...registerForm, password: event.target.value })
                    }
                  />
                </div>
                {message && <div className="status">{message}</div>}
                <div className="button-row">
                  <button type="button" className="primary" onClick={handleRegister}>
                    创建账号
                  </button>
                  <button type="button" onClick={() => showPage("login")}>
                    返回登录
                  </button>
                </div>
              </section>
            </div>
          </section>
        )}

        {page === "create" && (
          <section className="page active page--create">
            <div className="create-studio">
              <aside className="create-brand-panel">
                <span className="section-kicker">Knowledge Studio</span>
                <h1>创建 Knowledge Bar</h1>
                <p>
                  把一个主题整理成可持续生长的知识路径。先命名，再写简介和标签，之后进入编辑区沉淀内容。
                </p>
                <div className="node-orbit" aria-hidden="true">
                  <span className="node node-root">主题</span>
                  <span className="node node-a">文档</span>
                  <span className="node node-b">标签</span>
                  <span className="node node-c">导图</span>
                </div>
              </aside>
              <section className="create-form-panel form-card">
                <header className="create-mobile-header">
                  <button type="button" className="create-mobile-back" onClick={() => showPage("dashboard")} aria-label="返回">
                    ‹
                  </button>
                  <span className="create-mobile-title">新建 Bar</span>
                  <button
                    type="button"
                    className="create-mobile-submit"
                    onClick={submitCreate}
                    disabled={isCreating || !createForm.name.trim()}
                  >
                    {isCreating ? "创建中…" : "创建"}
                  </button>
                </header>
                <span className="section-kicker create-desktop-kicker">New Bar</span>
                <h2 className="create-desktop-title">创建 Knowledge Bar</h2>
                <div className="two-col-field">
                  <label htmlFor="kb-name">bar 名称</label>
                  <input
                    id="kb-name"
                    value={createForm.name}
                    placeholder="例如：考研政治强化复习"
                    onChange={(event) => setCreateForm({ ...createForm, name: event.target.value })}
                    onKeyDown={(event) => { if (event.key === "Enter") submitCreate(); }}
                  />
                </div>
                <div className="two-col-field">
                  <label htmlFor="kb-desc">介绍</label>
                  <textarea
                    id="kb-desc"
                    value={createForm.description}
                    placeholder="填写知识库介绍（选填）"
                    onChange={(event) =>
                      setCreateForm({ ...createForm, description: event.target.value })
                    }
                  />
                </div>
                <div className="two-col-field">
                  <label htmlFor="kb-tags">标签</label>
                  <input
                    id="kb-tags"
                    value={createForm.tags}
                    placeholder="例如：考研政治、英语、专业课"
                    onChange={(event) => setCreateForm({ ...createForm, tags: event.target.value })}
                  />
                </div>
                {message && <div className="status">{message}</div>}
                <div className="button-row create-desktop-buttons">
                  <button type="button" className="primary" onClick={submitCreate} disabled={isCreating}>
                    {isCreating ? "创建中…" : "创建并进入详情页"}
                  </button>
                  <button type="button" className="secondary" onClick={() => showPage("dashboard")}>
                    取消
                  </button>
                </div>
              </section>
            </div>
          </section>
        )}

        {page === "dashboard" && (
          <section className="page active">
            <div className={`surface app-layout dashboard-layout ${sidebarCollapsed ? "sidebar-collapsed" : ""}`}>
              <AccountSidebar
                collapsed={sidebarCollapsed}
                onCollapse={() => setSidebarCollapsed((value) => !value)}
                onShowPage={(p) => { showPage(p); setMobileSidebarOpen(false); }}
                email={session?.user.email}
                onSignOut={handleSignOut}
                avatarUrl={avatarUrl}
                mobileOpen={mobileSidebarOpen}
              />
              <section className="workspace dashboard-workspace">
                <div className="dashboard-hero">
                  <div>
                    <span className="section-kicker">Personal Knowledge Studio</span>
                    <h1>我的知识库</h1>
                    <p>把文档、标签、图片和灵感节点组织成一张可以继续生长的知识地图。</p>
                  </div>
                  <div className="dashboard-actions">
                    <button
                      type="button"
                      className="ai-map-entry"
                      onClick={() => navigate("/mindmap/new", { state: { from: "dashboard" } satisfies MindMapLocationState })}
                    >
                      <span className="ai-map-entry__badge">AI</span>
                      <RotatingText
                        texts={["AI 思维导图", "一键生成导图", "灵感节点连接"]}
                        mainClassName="ai-map-entry__rotating"
                        staggerFrom="last"
                        initial={{ y: "100%", opacity: 0 }}
                        animate={{ y: 0, opacity: 1 }}
                        exit={{ y: "-120%", opacity: 0 }}
                        staggerDuration={0.018}
                        transition={{ type: "spring", damping: 28, stiffness: 360 }}
                        rotationInterval={2200}
                      />
                      <span className="ai-map-entry__arrow">→</span>
                    </button>
                    <button type="button" className="primary" onClick={() => showPage("create")}>
                      创建 Knowledge Bar
                    </button>
                  </div>
                </div>
                <div className="summary-grid" aria-label="知识库摘要">
                  <div className="summary-card summary-card--orange">
                    <span>知识库</span>
                    <strong>{knowledgeBases.length}</strong>
                    <small>已创建主题</small>
                  </div>
                  <div className="summary-card">
                    <span>标签</span>
                    <strong>{uniqueTags.length}</strong>
                    <small>去重统计</small>
                  </div>
                  <div className="summary-card">
                    <span>文档</span>
                    <strong>{filledDocCount}</strong>
                    <small>已有内容</small>
                  </div>
                  <div className="summary-card summary-card--ink">
                    <span>最近更新</span>
                    <strong>{formatDateLabel(latestUpdatedAt)}</strong>
                    <small>来自保存记录</small>
                  </div>
                </div>
                {!isCloudMode && (
                  <div className="guest-ribbon">
                    游客本地体验中：登录后可把知识库保存到云端。
                  </div>
                )}
                <div className="search-row">
                  <input
                    id="search"
                    value={query}
                    placeholder="搜索知识库名称、描述、标签"
                    onChange={(event) => setQuery(event.target.value)}
                  />
                </div>

                {filteredKnowledgeBases.length === 0 ? (
                  <div className="state">
                    <h3>建立第一条知识路径</h3>
                    <div className="empty-state">
                      <div>
                        <div className="big-plus">+</div>
                        <button type="button" className="primary" onClick={() => showPage("create")}>
                          创建 Knowledge Bar
                        </button>
                        <p className="muted">从一个主题开始，逐步连接文档、标签和思维导图。</p>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="state">
                    <h3>我的知识库</h3>
                    <div className="card-grid">
                      {filteredKnowledgeBases.map((item, index) => (
                        <article
                          className="kb-card"
                          key={item.id}
                          style={{ ["--card-color" as string]: item.color }}
                          onClick={() => {
                            setCurrentId(item.id);
                            sessionStorage.setItem(
                              selectionStorageKey(knowledgeBaseScope(isCloudMode ? activeUserId : null)),
                              item.id,
                            );
                            showPage("detail");
                          }}
                        >
                          <button
                            type="button"
                            className="kb-card-delete"
                            onClick={(e) => {
                              e.stopPropagation();
                              setDeleteConfirmId(item.id);
                            }}
                            aria-label="删除知识库"
                          >
                            ×
                          </button>
                          <div className="kb-card-index">{String(index + 1).padStart(2, "0")}</div>
                          <div className="doc-stack" aria-hidden="true">
                            <span />
                            <span />
                            <span />
                          </div>
                          <h4>{item.name}</h4>
                          <p className="muted">{item.description || "暂无描述"}</p>
                          <div className="kb-meta-row">
                            <span>{formatDateLabel(item.updated_at)}</span>
                            <span>{item.content_md.trim().length > 0 ? "已写入内容" : "待补充内容"}</span>
                          </div>
                          <div className="tag-list">
                            {(item.tags?.length ? item.tags : [item.origin === "guest" ? "本地草稿" : "云端知识库"]).map((tag) => (
                              <span className="tag" key={tag}>
                                {tag}
                              </span>
                            ))}
                          </div>
                        </article>
                      ))}
                      <article
                        className="new-card"
                        role="button"
                        tabIndex={0}
                        onClick={() => showPage("create")}
                        onKeyDown={(event) => {
                          if (event.key === "Enter" || event.key === " ") {
                            event.preventDefault();
                            showPage("create");
                          }
                        }}
                      >
                        <div className="new-card-visual" aria-hidden="true">
                          <span className="new-card-line" />
                          <span className="new-card-node new-card-node--main">+</span>
                          <span className="new-card-node new-card-node--small new-card-node--top" />
                          <span className="new-card-node new-card-node--small new-card-node--bottom" />
                          <span className="new-card-sheet new-card-sheet--one" />
                          <span className="new-card-sheet new-card-sheet--two" />
                        </div>
                        <div className="new-card-copy">
                          <span className="new-card-kicker">New Knowledge Path</span>
                          <h4>新建 Knowledge Bar</h4>
                          <p>创建主题、沉淀资料，再生成思维导图。</p>
                        </div>
                        <span className="new-card-arrow" aria-hidden="true">→</span>
                      </article>
                    </div>
                  </div>
                )}
              </section>
            </div>
            {deleteConfirmId && (
              <div className="delete-overlay">
                <div className="delete-dialog">
                  <p>确认删除该知识库？此操作无法撤销。</p>
                  <div className="delete-dialog-actions">
                    <button
                      type="button"
                      className="delete-confirm-btn"
                      onClick={() => void confirmDeleteKnowledgeBase()}
                      disabled={isDeleting}
                    >
                      {isDeleting ? "删除中…" : "确认删除"}
                    </button>
                    <button
                      type="button"
                      className="delete-cancel-btn"
                      onClick={() => setDeleteConfirmId(null)}
                      disabled={isDeleting}
                    >
                      取消
                    </button>
                  </div>
                </div>
              </div>
            )}
          </section>
        )}

        {page === "settings" && (
          <section className="page active">
            <div className={`surface app-layout settings-layout ${sidebarCollapsed ? "sidebar-collapsed" : ""}`}>
              <AccountSidebar
                collapsed={sidebarCollapsed}
                onCollapse={() => setSidebarCollapsed((value) => !value)}
                onShowPage={(p) => { showPage(p); setMobileSidebarOpen(false); }}
                email={session?.user.email}
                onSignOut={handleSignOut}
                settingsMode
                avatarUrl={avatarUrl}
                mobileOpen={mobileSidebarOpen}
              />
              <section className="workspace settings-workspace">
                <div className="settings-hero">
                  <div className="settings-hero-copy">
                    <span className="section-kicker">Account Studio</span>
                    <h1>账号设置</h1>
                    <p>管理个人资料与登录状态，保持知识工作室的云端保存能力。</p>
                    <div className="settings-status-row" aria-label="账号状态">
                      <span>{isCloudMode ? "云端保存已连接" : "游客本地体验"}</span>
                      <span>{session?.user.email || "未登录邮箱"}</span>
                    </div>
                  </div>
                  <div className="settings-hero-map" aria-hidden="true">
                    <span className="settings-map-line settings-map-line--one" />
                    <span className="settings-map-line settings-map-line--two" />
                    <span className="settings-map-node settings-map-node--main">ID</span>
                    <span className="settings-map-node settings-map-node--cloud">云</span>
                    <span className="settings-map-node settings-map-node--lock">锁</span>
                    <span className="settings-map-card settings-map-card--one" />
                    <span className="settings-map-card settings-map-card--two" />
                  </div>
                </div>
                <div className="settings-card">
                  <div className="two-col-field">
                    <label htmlFor="setting-name">昵称</label>
                    <input id="setting-name" placeholder="输入昵称" />
                  </div>
                  <div className="two-col-field">
                    <label htmlFor="setting-email">邮箱</label>
                    <input id="setting-email" type="email" placeholder="用户邮箱" />
                  </div>
                  <div className="two-col-field">
                    <label htmlFor="setting-password">新密码</label>
                    <input id="setting-password" type="password" placeholder="需要修改密码时填写" />
                  </div>
                  <div className="button-row">
                    <button type="button" className="primary">
                      保存设置
                    </button>
                    <button type="button" className="secondary avatar-upload-btn" onClick={() => avatarInputRef.current?.click()}>上传头像</button>
                    <input
                      ref={avatarInputRef}
                      type="file"
                      accept="image/*"
                      hidden
                      onChange={(e) => { const f = e.target.files?.[0]; if (f) handleAvatarUpload(f); e.target.value = ""; }}
                    />
                    <button type="button" onClick={() => showPage("register")}>
                      游客注册/登录保存
                    </button>
                  </div>
                </div>
              </section>
            </div>
          </section>
        )}

        {page === "detail" && (
          <section className="page active">
            <div className={`surface app-layout detail-layout ${sidebarCollapsed ? "sidebar-collapsed" : ""}`}>
              <aside className={`sidebar detail-sidebar ${mobileSidebarOpen ? "mobile-open" : ""}`}>
                <div className="sidebar-content">
                  <div className="side-menu side-menu--top">
                    <button type="button" onClick={() => { showPage("dashboard"); setMobileSidebarOpen(false); }}>
                      返回知识库
                    </button>
                  </div>
                  <span className="section-kicker">Current Bar</span>
                  <h3>{currentKb?.name || "考研政治"}</h3>
                  <p>描述：{currentKb?.description || "强化复习阶段的知识库。"}</p>
                  <div className="detail-side-stats">
                    <span>{currentTags.length} 标签</span>
                    <span>{docContent.length} 字符</span>
                    <span>{currentKb ? formatDateLabel(currentKb.updated_at) : "本地草稿"}</span>
                  </div>
                  {currentTags.length > 0 && (
                    <div className="tag-list sidebar-tags">
                      {currentTags.map((tag) => (
                        <span className="tag" key={tag}>
                          {tag}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
                <button
                  type="button"
                  className="collapse-btn"
                  aria-label={sidebarCollapsed ? "展开侧栏" : "收起侧栏"}
                  onClick={() => setSidebarCollapsed((value) => !value)}
                >
                  {sidebarCollapsed ? "›" : "‹"}
                </button>
              </aside>
              <section className="workspace detail-workspace">
                <div className="mobile-editor-header">
                  <button type="button" aria-label="返回知识库" onClick={() => showPage("dashboard")}>←</button>
                  <strong>{currentKb?.name || "未命名 Knowledge Bar"}</strong>
                  <button
                    type="button"
                    aria-label="更多编辑操作"
                    aria-expanded={mobileEditorMenuOpen}
                    onClick={() => setMobileEditorMenuOpen((value) => !value)}
                  >
                    ⋯
                  </button>
                  {mobileEditorMenuOpen && (
                    <div className="mobile-editor-menu">
                      <button type="button" onClick={() => { setMessage(currentKb ? "已保存" : "请先创建知识库"); setMobileEditorMenuOpen(false); }}>保存</button>
                      <button type="button" onClick={() => { setMobileEditorMenuOpen(false); void renameCurrentKnowledgeBase(); }}>重命名</button>
                      <button type="button" onClick={() => { setMobileEditorMenuOpen(false); exportMarkdown(); }}>导出 MD</button>
                      <button type="button" onClick={() => { setMobileEditorMenuOpen(false); exportWord(); }}>导出 Word</button>
                    </div>
                  )}
                </div>
                <div className="detail-hero">
                  <div>
                    <span className="section-kicker">Knowledge Desk</span>
                    <h1>{currentKb?.name || "未命名 Knowledge Bar"}</h1>
                    <p>{currentKb?.description || "在这里记录内容、添加图片和标签，并生成可编辑思维导图。"}</p>
                  </div>
                  <div className="detail-node-map" aria-hidden="true">
                    <span>文档</span>
                    <span>标签</span>
                    <span>AI 导图</span>
                  </div>
                </div>
                <div className="editor-nav">
                  <span className="nav-title">编辑与输出</span>
                  <span className="spacer" />
                  <input
                    ref={imageInputRef}
                    className="visually-hidden"
                    type="file"
                    accept="image/*"
                    onChange={(event) => {
                      void handleImageFileInput(event.target.files?.[0]);
                      event.currentTarget.value = "";
                    }}
                  />
                  <button type="button" className="btn-image" onClick={() => imageInputRef.current?.click()}>
                    添加图片
                  </button>
                  <button type="button" className="btn-tag" onClick={() => void addSelectedTextAsTag()}>
                    添加标签
                  </button>
                  <button
                    type="button"
                    className="btn-save"
                    onClick={() => setMessage(currentKb ? "已保存" : "请先创建知识库")}
                  >
                    保存
                  </button>
                  <button type="button" className="primary btn-generate" onClick={() => {
                    const text = docEditorRef.current?.innerText?.trim() || "";
                    navigate("/mindmap/new", {
                      state: {
                        initialText: text,
                        from: "detail",
                        knowledgeBaseId: currentKb?.id ?? currentId ?? undefined,
                      } satisfies MindMapLocationState,
                    });
                  }}>
                    生成思维导图
                  </button>
                  <button type="button" className="btn-export" onClick={exportMarkdown}>
                    导出 MD
                  </button>
                  <button type="button" className="btn-export" onClick={exportWord}>
                    导出 Word
                  </button>
                  <button type="button" className="btn-rename" onClick={() => void renameCurrentKnowledgeBase()}>重命名</button>
                </div>
                <p className="muted">
                  像空白 Word 文档一样直接写。选中文字后点击“添加标签”。图片可以通过“添加图片”上传，后续实现时也支持复制图片后粘贴。
                </p>
                {message && <div className="status">{message}</div>}
                {currentTags.length > 0 && (
                  <div className="conditional-box tag-list">
                    {currentTags.map((tag) => (
                      <span className="tag" key={tag}>
                        {tag}
                      </span>
                    ))}
                  </div>
                )}
                <div
                  ref={docEditorRef}
                  className="doc doc-editor"
                  aria-label="自由知识库编辑区"
                  data-placeholder={
                    "在这里直接输入或粘贴你的知识内容。\n\n可以写标题、段落、列表、重点标记，也可以后续插入图片。\n\nAI 会基于这份自由文档生成一张可编辑的思维导图。"
                  }
                  onSelect={rememberSelectedText}
                  onBlur={rememberSelectedText}
                  onKeyDown={handleEditorKeyDown}
                  onKeyUp={rememberSelectedText}
                  onMouseUp={handleEditorMouseUp}
                  onClick={handleEditorClick}
                  onInput={handleEditorInput}
                  onPaste={handleEditorPaste}
                  contentEditable
                  suppressContentEditableWarning
                />
                <div className="editor-bottom-toolbar">
                  <button type="button" className="toolbar-cta-generate" aria-label="AI生成思维导图" onClick={() => {
                    const text = docEditorRef.current?.innerText?.trim() || "";
                    navigate("/mindmap/new", {
                      state: {
                        initialText: text,
                        from: "detail",
                        knowledgeBaseId: currentKb?.id ?? currentId ?? undefined,
                      } satisfies MindMapLocationState,
                    });
                  }}>
                    <span className="toolbar-icon">✨</span>
                    <span className="toolbar-label">AI生成</span>
                  </button>
                  <button type="button" aria-label="添加图片" onClick={() => imageInputRef.current?.click()}>
                    <span className="toolbar-icon">🖼</span>
                    <span className="toolbar-label">图片</span>
                  </button>
                  <button type="button" aria-label="添加标签" onClick={() => void addSelectedTextAsTag()}>
                    <span className="toolbar-icon">🏷</span>
                    <span className="toolbar-label">标签</span>
                  </button>
                  <button type="button" aria-label="导出" onClick={exportMarkdown}>
                    <span className="toolbar-icon">↗</span>
                    <span className="toolbar-label">导出</span>
                  </button>
                  <button type="button" aria-label="重命名" onClick={() => void renameCurrentKnowledgeBase()}>
                    <span className="toolbar-icon">✎</span>
                    <span className="toolbar-label">重命名</span>
                  </button>
                </div>
              </section>
            </div>
          </section>
        )}
      </main>
    </div>
  );
}

function AccountSidebar({
  collapsed,
  onCollapse,
  onShowPage,
  email,
  onSignOut,
  settingsMode = false,
  avatarUrl,
  mobileOpen = false,
}: {
  collapsed: boolean;
  onCollapse: () => void;
  onShowPage: (page: PageId) => void;
  email?: string;
  onSignOut: () => void;
  settingsMode?: boolean;
  avatarUrl?: string | null;
  mobileOpen?: boolean;
}) {
  const nickname = email ? email.split("@")[0] : "昵称 / 游客";
  return (
    <aside className={`sidebar ${mobileOpen ? "mobile-open" : ""}`}>
      <div className="sidebar-content" hidden={collapsed}>
        <div className="avatar">
          {avatarUrl ? <img src={avatarUrl} alt="头像" style={{ width: "100%", height: "100%", borderRadius: "50%", objectFit: "cover" }} /> : "头像"}
        </div>
        <h3>{nickname}</h3>
        {!settingsMode && (
          <p>{email ? "已登录：知识库会保存到云端。" : "游客模式提示：登录后可云端保存知识库。"}</p>
        )}
        <div className="side-menu">
          {settingsMode ? (
            <button type="button" onClick={() => onShowPage("dashboard")}>
              返回首页
            </button>
          ) : (
            <button type="button" onClick={() => onShowPage("settings")}>
              设置
            </button>
          )}
          <button type="button" onClick={onSignOut}>
            退出登录
          </button>
        </div>
      </div>
      <button
        type="button"
        className="collapse-btn"
        aria-label={collapsed ? "展开侧栏" : "收起侧栏"}
        onClick={onCollapse}
      >
        {collapsed ? "›" : "‹"}
      </button>
    </aside>
  );
}
