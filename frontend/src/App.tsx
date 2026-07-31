import { useEffect, useMemo, useRef, useState, type ClipboardEvent } from "react";
import { Routes, Route, useNavigate, useParams } from "react-router-dom";
import type { Session } from "@supabase/supabase-js";
import { exportWordDocument } from "./lib/api";
import {
  getCloudSession,
  listCloudKnowledgeBases,
  saveCloudKnowledgeBase,
  signInWithEmail,
  signOutCloud,
  signUpWithEmail,
  uploadCloudAttachment,
} from "./lib/cloudStore";
import {
  listGuestKnowledgeBases,
  saveGuestKnowledgeBase,
} from "./lib/guestStore";
import { hasSupabaseConfig } from "./lib/supabase";
import MindMapPage from "./pages/MindMapPage";
import "./styles/mindmap.css";
import type { KnowledgeBase } from "./types";

type PageId = "login" | "register" | "create" | "dashboard" | "settings" | "detail" | "mindmap";

const now = () => new Date().toISOString();
const defaultColor = "#ff6d29";


const imageMarkdownPattern = /!\[([^\]]*)\]\(([^)]+)\)/g;

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
    const [token, alt = "", src = ""] = match;
    const index = match.index ?? 0;
    html += textToEditorHtml(markdown.slice(lastIndex, index));
    html += `<figure class="doc-image-block" contenteditable="false"><img src="${escapeHtml(src)}" alt="${escapeHtml(
      alt,
    )}" /><figcaption>${escapeHtml(alt || "image")}</figcaption></figure>`;
    lastIndex = index + token.length;
  }
  html += textToEditorHtml(markdown.slice(lastIndex));
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
      return src ? `\n\n![${alt}](${src})\n\n` : "";
    }

    const content = Array.from(node.childNodes).map(walk).join("");
    if (["DIV", "P", "LI"].includes(node.tagName)) return `${content}\n`;
    return content;
  }

  return Array.from(root.childNodes).map(walk).join("").replace(/\n{3,}/g, "\n\n").trim();
}

function sanitizeImageName(name: string): string {
  return name.replace(/[\[\]\r\n]/g, " ").trim() || "image";
}

function splitTags(value: string): string[] {
  return value
    .split(/[，,、\s]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function createKnowledgeBase(input: { name: string; description: string; tags: string }): KnowledgeBase {
  const timestamp = now();
  return {
    id: crypto.randomUUID(),
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
  return (
    <div className="shell">
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
        <MindMapPage onBack={() => navigate("/")} taskId={taskId === "new" ? undefined : taskId} />
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
  const [page, setPage] = useState<PageId>("login");
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [currentId, setCurrentId] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [query, setQuery] = useState("");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [guestDraftContent, setGuestDraftContent] = useState("");
  const [guestDraftTags, setGuestDraftTags] = useState<string[]>([]);
  const [selectedDocText, setSelectedDocText] = useState("");
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const docEditorRef = useRef<HTMLDivElement | null>(null);
  const lastEditorContentRef = useRef("");
  const [loginForm, setLoginForm] = useState({
    email: "",
    password: "",
  });
  const [registerForm, setRegisterForm] = useState({
    email: "",
    password: "",
    confirmPassword: "",
  });
  const [createForm, setCreateForm] = useState({
    name: "",
    description: "",
    tags: "",
  });

  useEffect(() => {
    bootstrapSession();
  }, []);

  async function bootstrapSession() {
    try {
      const savedSession = await getCloudSession();
      setSession(savedSession);
      await refreshKnowledgeBases(savedSession?.user.id);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "云端会话读取失败，已切换游客模式。");
      await refreshKnowledgeBases();
    }
  }

  async function refreshKnowledgeBases(targetUserId: string | null | undefined = session?.user.id) {
    const items =
      hasSupabaseConfig && targetUserId
        ? await listCloudKnowledgeBases(targetUserId)
        : await listGuestKnowledgeBases();
    setKnowledgeBases(items);
    if (!currentId && items[0]) {
      setCurrentId(items[0].id);
    }
  }

  function showPage(next: PageId) {
    setMessage("");
    setPage(next);
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

  useEffect(() => {
    if (page !== "detail") return;
    const editor = docEditorRef.current;
    if (!editor) return;
    if (lastEditorContentRef.current === docContent && editor.innerHTML) return;
    editor.innerHTML = markdownToEditorHtml(docContent);
    lastEditorContentRef.current = docContent;
  }, [currentId, docContent, page]);

  async function persistKnowledgeBase(kb: KnowledgeBase) {
    if (isCloudMode && activeUserId) {
      await saveCloudKnowledgeBase(kb, activeUserId);
    } else {
      await saveGuestKnowledgeBase(kb);
    }
  }


  async function handleLogin() {
    if (!hasSupabaseConfig) {
      setMessage("当前未配置 Supabase，已使用游客模式体验。");
      showPage("dashboard");
      return;
    }
    try {
      const nextSession = await signInWithEmail(loginForm.email.trim(), loginForm.password);
      setSession(nextSession);
      await refreshKnowledgeBases(nextSession.user.id);
      showPage("dashboard");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "登录失败，请稍后重试。");
    }
  }

  async function handleRegister() {
    if (registerForm.password !== registerForm.confirmPassword) {
      setMessage("两次输入的密码不一致。");
      return;
    }
    if (!hasSupabaseConfig) {
      setMessage("当前未配置 Supabase，暂时只能游客体验。");
      return;
    }
    try {
      const nextSession = await signUpWithEmail(registerForm.email.trim(), registerForm.password);
      if (!nextSession) {
        setMessage("注册已提交，请确认邮箱后再登录；若要第一版免验证，请在 Supabase 关闭邮箱确认。");
        setPage("login");
        window.scrollTo({ top: 0, behavior: "smooth" });
        return;
      }
      setSession(nextSession);
      await refreshKnowledgeBases(nextSession.user.id);
      showPage("dashboard");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "注册失败，请稍后重试。");
    }
  }

  async function handleSignOut() {
    try {
      await signOutCloud();
      setSession(null);
      await refreshKnowledgeBases(null);
      showPage("login");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "退出登录失败，请重试。");
    }
  }

  async function submitCreate() {
    if (!createForm.name.trim()) {
      setMessage("请输入 bar 名称。");
      return;
    }
    const kb = createKnowledgeBase({
      name: createForm.name.trim(),
      description: createForm.description.trim(),
      tags: createForm.tags,
    });
    await persistKnowledgeBase(kb);
    setCurrentId(kb.id);
    setKnowledgeBases((items) => [kb, ...items]);
    setCreateForm({ name: "", description: "", tags: "" });
    showPage("detail");
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
    void saveCurrentContent(nextContent);
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
      const blob = await exportWordDocument({ title, markdown: source });
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
      const body = escapeHtml(source || "暂无内容").replace(/\n/g, "<br>");
      const html = `<!doctype html><html><head><meta charset="utf-8"><title>${escapeHtml(
        title,
      )}</title></head><body><h1>${escapeHtml(title)}</h1><p>${body}</p></body></html>`;
      downloadTextFile(`${title}.doc`, html, "application/msword;charset=utf-8");
      setMessage("后端暂不可用，已导出 Word 兼容文件。");
    }
  }

  return (
    <div className="shell">
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
      </header>

      <main>
        {page === "login" && (
          <section className="page active">
            <div className="surface hero-slab">
              <section className="hero-blue">
                <div className="kicker">Open study bar / AI mind map</div>
                <h1>Knowledge Bar</h1>
                <p className="hero-copy">
                  把零散笔记调成一杯清醒的知识鸡尾酒。输入文字，沉淀资料，让 AI 生成可编辑的思维导图。
                </p>
              </section>
              <section className="login-panel">
                <h2 className="panel-title">进入 Knowledge Bar</h2>
                <p className="panel-desc">邮箱密码登录。也可以先跳过体验，登录后再保存到云端。</p>
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
                  />
                </div>
                {message && <div className="status">{message}</div>}
                <div className="button-row">
                  <button type="button" className="primary" onClick={handleLogin}>
                    登录
                  </button>
                  <button type="button" className="ghost" onClick={() => showPage("dashboard")}>
                    跳过体验
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
            <div className="surface hero-slab">
              <section className="hero-blue">
                <div className="kicker">Create your own bar</div>
                <h1>开一间自己的知识酒吧</h1>
                <p className="hero-copy">
                  第一版不做邮箱验证，降低使用门槛。后续可补充忘记密码、使用次数和会员能力。
                </p>
              </section>
              <section className="login-panel">
                <h2 className="panel-title">创建账号</h2>
                <p className="panel-desc">只需要邮箱和密码。</p>
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
                <div className="field">
                  <label htmlFor="register-confirm">确认密码</label>
                  <input
                    id="register-confirm"
                    type="password"
                    value={registerForm.confirmPassword}
                    placeholder="再次输入密码"
                    onChange={(event) =>
                      setRegisterForm({ ...registerForm, confirmPassword: event.target.value })
                    }
                  />
                </div>
                {message && <div className="status">{message}</div>}
                <div className="button-row">
                  <button type="button" className="primary" onClick={handleRegister}>
                    注册并登录
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
          <section className="page active">
            <div className="form-card">
              <h2>创建 knowledge bar</h2>
              <div className="two-col-field">
                <label htmlFor="kb-name">bar 名称</label>
                <input
                  id="kb-name"
                  value={createForm.name}
                  placeholder="例如：考研政治强化复习"
                  onChange={(event) => setCreateForm({ ...createForm, name: event.target.value })}
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
              <div className="button-row">
                <button type="button" className="primary" onClick={submitCreate}>
                  创建并进入详情页
                </button>
                <button type="button" onClick={() => showPage("dashboard")}>
                  取消
                </button>
              </div>
            </div>
          </section>
        )}

        {page === "dashboard" && (
          <section className="page active">
            <div className={`surface app-layout ${sidebarCollapsed ? "sidebar-collapsed" : ""}`}>
              <AccountSidebar
                collapsed={sidebarCollapsed}
                onCollapse={() => setSidebarCollapsed((value) => !value)}
                onShowPage={showPage}
                email={session?.user.email}
                onSignOut={handleSignOut}
              />
              <section className="workspace">
                <div className="workspace-bar">
                  <h2>我的 knowledge bar</h2>
                  <span className="spacer" />
                  <button type="button" className="primary" onClick={() => {
                    navigate("/mindmap/new");
                  }}>
                    思维导图
                  </button>
                </div>
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
                    <h3>暂无知识库</h3>
                    <div className="empty-state">
                      <div>
                        <div className="big-plus">+</div>
                        <button type="button" className="primary" onClick={() => showPage("create")}>
                          创建 knowledge bar
                        </button>
                        <p className="muted">暂无知识库时，优先引导用户创建。</p>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="state">
                    <h3>我的知识库</h3>
                    <div className="card-grid">
                      {filteredKnowledgeBases.map((item) => (
                        <article
                          className="kb-card"
                          key={item.id}
                          style={{ ["--card-color" as string]: item.color }}
                          onClick={() => {
                            setCurrentId(item.id);
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
                          <h4>{item.name}</h4>
                          <p className="muted">{item.description || "暂无描述"}</p>
                          <div className="tag-list">
                            {(item.tags?.length ? item.tags : ["本地草稿"]).map((tag) => (
                              <span className="tag" key={tag}>
                                {tag}
                              </span>
                            ))}
                          </div>
                        </article>
                      ))}
                      <article className="new-card" onClick={() => showPage("create")}>
                        <div>
                          <div className="big-plus">+</div>
                          <h4>新建</h4>
                        </div>
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
                      onClick={() => {
                        setKnowledgeBases((items) => items.filter((kb) => kb.id !== deleteConfirmId));
                        if (currentId === deleteConfirmId) setCurrentId(null);
                        setDeleteConfirmId(null);
                      }}
                    >
                      确认删除
                    </button>
                    <button
                      type="button"
                      className="delete-cancel-btn"
                      onClick={() => setDeleteConfirmId(null)}
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
            <div className={`surface app-layout ${sidebarCollapsed ? "sidebar-collapsed" : ""}`}>
              <AccountSidebar
                collapsed={sidebarCollapsed}
                onCollapse={() => setSidebarCollapsed((value) => !value)}
                onShowPage={showPage}
                email={session?.user.email}
                onSignOut={handleSignOut}
                settingsMode
              />
              <section className="workspace">
                <div className="workspace-bar">
                  <h2>账号设置</h2>
                </div>
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
                  <button type="button">上传头像</button>
                  <button type="button" onClick={() => showPage("register")}>
                    游客注册/登录保存
                  </button>
                </div>
              </section>
            </div>
          </section>
        )}

        {page === "detail" && (
          <section className="page active">
            <div className={`surface app-layout ${sidebarCollapsed ? "sidebar-collapsed" : ""}`}>
              <aside className="sidebar">
                <div className="sidebar-content">
                  <h3>{currentKb?.name || "考研政治"}</h3>
                  <p>描述：{currentKb?.description || "强化复习阶段的知识库。"}</p>
                  {currentTags.length > 0 && (
                    <div className="tag-list sidebar-tags">
                      {currentTags.map((tag) => (
                        <span className="tag" key={tag}>
                          {tag}
                        </span>
                      ))}
                    </div>
                  )}
                  <div className="side-menu">
                    <button type="button" onClick={() => showPage("dashboard")}>
                      {"<<<"} 返回
                    </button>
                  </div>
                </div>
                <button
                  type="button"
                  className="collapse-btn"
                  onClick={() => setSidebarCollapsed((value) => !value)}
                >
                  {sidebarCollapsed ? ">>>" : "<<<"}
                </button>
              </aside>
              <section className="workspace">
                <div className="editor-nav">
                  <span className="spacer" />
                  <button
                    type="button"
                    onClick={() => setMessage(currentKb ? "已保存" : "请先创建知识库")}
                  >
                    保存
                  </button>
                  <button type="button" className="primary" onClick={() => {
                    navigate("/mindmap/new");
                  }}>
                    生成思维导图
                  </button>
                  <button type="button" onClick={exportMarkdown}>
                    导出 MD
                  </button>
                  <button type="button" onClick={exportWord}>
                    导出 Word
                  </button>
                  <button type="button">重命名</button>
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
                  onKeyUp={rememberSelectedText}
                  onMouseUp={rememberSelectedText}
                  onInput={handleEditorInput}
                  onPaste={handleEditorPaste}
                  contentEditable
                  suppressContentEditableWarning
                />
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
}: {
  collapsed: boolean;
  onCollapse: () => void;
  onShowPage: (page: PageId) => void;
  email?: string;
  onSignOut: () => void;
  settingsMode?: boolean;
}) {
  const nickname = email ? email.split("@")[0] : "昵称 / 游客";
  return (
    <aside className="sidebar">
      <div className="sidebar-content" hidden={collapsed}>
        <div className="avatar">头像</div>
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
      <button type="button" className="collapse-btn" onClick={onCollapse}>
        {collapsed ? ">>>" : "<<<"}
      </button>
    </aside>
  );
}

