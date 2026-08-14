/**
 * Mind Map page - V2 implementation using /api/ai/* endpoints.
 * Guests are blocked from generation and prompted to log in.
 */

import { useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState, forwardRef } from "react";
import { useNavigate } from "react-router-dom";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  Position,
  type Node,
  type Edge,
  MarkerType,
  ReactFlowProvider,
  useReactFlow,
  getNodesBounds,
  getViewportForBounds,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { toPng } from "html-to-image";
import { getCloudSession } from "../lib/cloudStore";
import { supabase } from "../lib/supabase";
import { trackEvent, setAnalyticsToken } from "../lib/analytics";
import {
  generateMindMap,
  regenerateMindMap,
  getLatestMindMap,
  listMindMapVersions,
  patchMindMap,
  deleteMindMap,
  type LatestMindMapResponse,
  type MindMapVersionItem,
} from "../lib/api";

// --- Types ---
type MindMapReturnState = {
  initialText?: string;
  from?: "dashboard" | "detail";
  knowledgeBaseId?: string;
};

type GenerationStep =
  | "idle"
  | "preparing"
  | "extracting"
  | "validating"
  | "rendering"
  | "done"
  | "failed";

const STEP_LABELS: Record<GenerationStep, string> = {
  idle: "",
  preparing: "正在整理原文...",
  extracting: "正在提取知识点...",
  validating: "正在检查导图...",
  rendering: "正在生成导图...",
  done: "生成完成",
  failed: "生成失败",
};

// --- Helpers ---
function mindMapToFlowNodes(data: LatestMindMapResponse): { nodes: Node[]; edges: Edge[] } {
  const nodeMap = new Map(data.mind_map.nodes.map((n) => [n.id, n]));
  const childrenByParent = new Map<string | null, typeof data.mind_map.nodes>();
  for (const node of data.mind_map.nodes) {
    const list = childrenByParent.get(node.parentId) || [];
    list.push(node);
    childrenByParent.set(node.parentId, list);
  }

  const positions = new Map<string, { x: number; y: number; level: number }>();
  function layout(parentId: string | null, x: number, y: number, level: number): number {
    const children = childrenByParent.get(parentId) || [];
    children.sort((a, b) => a.order - b.order);
    let currentY = y;
    for (const child of children) {
      positions.set(child.id, { x: x + level * 280, y: currentY, level });
      const subtreeHeight = layout(child.id, x, currentY, level + 1);
      currentY += Math.max(subtreeHeight, 80);
    }
    return currentY - y || 60;
  }

  const root = data.mind_map.nodes.find((n) => n.parentId === null);
  if (root) {
    positions.set(root.id, { x: 0, y: 0, level: 0 });
    layout(root.id, 0, 0, 1);
    const allY = Array.from(positions.values()).map((p) => p.y);
    const midY = (Math.min(...allY) + Math.max(...allY)) / 2;
    const rootPos = positions.get(root.id)!;
    rootPos.y = midY;
  }

  const flowNodes: Node[] = data.mind_map.nodes.map((n) => {
    const pos = positions.get(n.id) || { x: 0, y: 0, level: 0 };
    const level = pos.level;
    return {
      id: n.id,
      position: { x: pos.x, y: pos.y },
      data: { label: n.text, level },
      type: "default",
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
      style: {
        width: level === 0 ? 200 : level === 1 ? 180 : 160,
        minHeight: 40,
        background: level === 0 ? "#FF6A1A" : level === 1 ? (n.order % 3 === 0 ? "#171513" : "#FFE2CF") : "#FFFFFF",
        color: level === 0 ? "#fff" : level === 1 && n.order % 3 === 0 ? "#fff" : "#171513",
        border: level === 0 ? "2px solid #E9510E" : level === 1 ? "1.5px solid #FF813F" : "1px solid #FFB98F",
        borderRadius: level === 0 ? "22px" : level === 1 ? "18px" : "14px",
        padding: "12px 16px",
        fontSize: level === 0 ? "16px" : "13px",
        fontWeight: level === 0 ? "800" : level === 1 ? "700" : "500",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        textAlign: "center" as const,
        lineHeight: "1.4",
        boxShadow: level === 0 ? "0 18px 34px rgba(255,106,26,0.24)" : "0 10px 24px rgba(23,21,19,0.08)",
      },
    };
  });

  const flowEdges: Edge[] = data.mind_map.nodes
    .filter((n) => n.parentId !== null)
    .map((n) => ({
      id: `edge-${n.parentId}-${n.id}`,
      source: n.parentId!,
      target: n.id,
      type: "smoothstep",
      style: { stroke: n.order % 2 === 0 ? "#FF813F" : "#4A4541", strokeWidth: 1.8 },
      markerEnd: { type: MarkerType.ArrowClosed, color: n.order % 2 === 0 ? "#FF813F" : "#4A4541", width: 12, height: 12 },
    }));

  return { nodes: flowNodes, edges: flowEdges };
}

// --- Flow Inner Component ---
export interface FlowCanvasHandle {
  exportPng: () => Promise<string | null>;
}

const FlowCanvas = forwardRef<FlowCanvasHandle, {
  flowNodes: Node[];
  flowEdges: Edge[];
  onNodeDoubleClick: (id: string, newText: string) => void;
}>(function FlowCanvas({ flowNodes, flowEdges, onNodeDoubleClick }, ref) {
  const [nodes, setNodes, onNodesChange] = useNodesState(flowNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(flowEdges);
  const { fitView, getNodes } = useReactFlow();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editText, setEditText] = useState("");

  useEffect(() => {
    setNodes(flowNodes);
    setEdges(flowEdges);
    setTimeout(() => fitView({ padding: 0.2 }), 50);
  }, [flowNodes, flowEdges, setNodes, setEdges, fitView]);

  useImperativeHandle(ref, () => ({
    exportPng: async () => {
      const nodesBounds = getNodesBounds(getNodes());
      const padding = 50;
      const width = nodesBounds.width + padding * 2;
      const height = nodesBounds.height + padding * 2;
      const viewport = getViewportForBounds(nodesBounds, width, height, 0.5, 2, 0.2);
      const el = document.querySelector(".react-flow__viewport") as HTMLElement;
      if (!el) return null;
      const prev = el.style.transform;
      el.style.transform = `translate(${viewport.x + padding}px, ${viewport.y + padding}px) scale(${viewport.zoom})`;
      try {
        const dataUrl = await toPng(el, {
          backgroundColor: "#FFFCF9",
          width,
          height,
          style: {
            width: `${width}px`,
            height: `${height}px`,
            transform: `translate(${viewport.x + padding}px, ${viewport.y + padding}px) scale(${viewport.zoom})`,
          },
        });
        return dataUrl;
      } finally {
        el.style.transform = prev;
      }
    },
  }), [getNodes]);

  const commitEdit = useCallback(() => {
    if (editingId && editText.trim()) {
      onNodeDoubleClick(editingId, editText.trim());
    }
    setEditingId(null);
    setEditText("");
  }, [editingId, editText, onNodeDoubleClick]);

  return (
    <>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeDoubleClick={(_, node) => {
          setEditingId(node.id);
          setEditText(node.data.label as string);
        }}
        onPaneClick={() => { if (editingId) commitEdit(); }}
        fitView
        minZoom={0.15}
        maxZoom={2}
        panOnDrag
        zoomOnPinch
        zoomOnScroll
        zoomOnDoubleClick={false}
        nodesDraggable={false}
        elementsSelectable
        proOptions={{ hideAttribution: true }}
      >
      <Background gap={22} color="#F0D8C8" />
      <Controls showInteractive={false} />
      <MiniMap
        pannable
        zoomable
        style={{ background: "#FFF8F3", border: "1px solid #F0C8AE", borderRadius: 16 }}
      />
    </ReactFlow>
    {editingId && (
      <div style={{
        position: "absolute",
        top: 0, left: 0, right: 0, bottom: 0,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "rgba(255, 248, 243, 0.72)",
        zIndex: 10,
        padding: "16px",
      }} onClick={commitEdit}>
        <input
          autoFocus
          value={editText}
          onChange={(e) => setEditText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") commitEdit();
            if (e.key === "Escape") { setEditingId(null); setEditText(""); }
          }}
          onClick={(e) => e.stopPropagation()}
          style={{
            width: "min(300px, calc(100vw - 48px))",
            padding: "12px 16px",
            fontSize: "15px",
            background: "#FFFFFF",
            color: "#171513",
            border: "2px solid #FF6A1A",
            borderRadius: "14px",
            outline: "none",
            textAlign: "center",
          }}
        />
      </div>
    )}
    </>
  );
});

// --- Main Page Component ---
export default function MindMapPage({
  onBack,
  initialText,
  knowledgeBaseId,
  returnState,
  taskId: _taskId,
}: {
  onBack?: () => void;
  initialText?: string;
  knowledgeBaseId?: string;
  returnState?: MindMapReturnState;
  taskId?: string;
}) {
  const navigate = useNavigate();
  const [inputText, setInputText] = useState(initialText || "");
  const [inputTitle, setInputTitle] = useState("");

  const [currentData, setCurrentData] = useState<LatestMindMapResponse | null>(null);
  const [flowNodes, setFlowNodes] = useState<Node[]>([]);
  const [flowEdges, setFlowEdges] = useState<Edge[]>([]);

  const [step, setStep] = useState<GenerationStep>("idle");
  const [errorMsg, setErrorMsg] = useState("");
  const [generating, setGenerating] = useState(false);
  const [showLoginPrompt, setShowLoginPrompt] = useState(false);

  const [versions, setVersions] = useState<MindMapVersionItem[]>([]);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [activeGenerationId, setActiveGenerationId] = useState<string | null>(null);
  const [feedbackGiven, setFeedbackGiven] = useState(false);
  const [requestedMaxDepth, setRequestedMaxDepth] = useState(5);

  const flowCanvasRef = useRef<FlowCanvasHandle>(null);
  const autoTriggered = useRef(false);

  const effectiveKbId = knowledgeBaseId || returnState?.knowledgeBaseId;

  const preservedReturnState = useMemo(() => {
    if (!returnState?.from && !returnState?.knowledgeBaseId) return undefined;
    return {
      from: returnState?.from,
      knowledgeBaseId: returnState?.knowledgeBaseId,
    } satisfies MindMapReturnState;
  }, [returnState]);

  // Load existing mind map if we have a KB ID
  useEffect(() => {
    if (effectiveKbId && !currentData && !autoTriggered.current) {
      (async () => {
        const session = await getCloudSession();
        if (!session?.access_token) return;
        try {
          const latest = await getLatestMindMap({ knowledge_base_id: effectiveKbId, token: session.access_token });
          applyResponse(latest);
          setStep("done");
          loadVersions(session.access_token);
        } catch {
          // No existing mind map — that's fine, user can generate
        }
      })();
    }
  }, [effectiveKbId]);

  const loadVersions = useCallback(async (token: string) => {
    if (!effectiveKbId) return;
    try {
      const items = await listMindMapVersions({ knowledge_base_id: effectiveKbId, token });
      setVersions(items);
    } catch {
      // ignore
    }
  }, [effectiveKbId]);

  const applyResponse = useCallback((data: LatestMindMapResponse) => {
    setCurrentData(data);
    const { nodes, edges } = mindMapToFlowNodes(data);
    setFlowNodes(nodes);
    setFlowEdges(edges);
  }, []);

  // Generate
  const handleGenerate = useCallback(async () => {
    const text = inputText.trim();
    if (!text) {
      setErrorMsg("请输入文本内容");
      return;
    }
    if (text.length < 20) {
      setErrorMsg("文本内容过短，请输入至少20字");
      return;
    }

    const session = await getCloudSession();
    if (!session?.access_token) {
      setShowLoginPrompt(true);
      return;
    }

    let kbId = effectiveKbId;
    if (!kbId) {
      if (!supabase) {
        setErrorMsg("请先保存知识库再生成导图");
        return;
      }
      const newId = crypto.randomUUID();
      const { error } = await supabase.from("knowledge_bases").insert({
        id: newId,
        user_id: session.user.id,
        name: inputTitle.trim() || "知识导图",
        description: "",
        color: "#ff6d29",
        content_md: text,
        updated_at: new Date().toISOString(),
      });
      if (error) {
        setErrorMsg("创建知识库失败：" + error.message);
        return;
      }
      kbId = newId;
    }

    setGenerating(true);
    setErrorMsg("");
    setStep("preparing");
    setFeedbackGiven(false);
    setAnalyticsToken(session.access_token);

    trackEvent({
      event_name: "mindmap_generate_clicked",
      knowledge_base_id: kbId,
      properties: { input_length: text.length, requested_max_depth: requestedMaxDepth },
    });

    const stepTimer = setTimeout(() => setStep("extracting"), 800);
    const stepTimer2 = setTimeout(() => setStep("validating"), 2500);
    const stepTimer3 = setTimeout(() => setStep("rendering"), 4000);

    try {
      const result = await generateMindMap({
        knowledge_base_id: kbId,
        title: inputTitle.trim() || "知识导图",
        description: "",
        content_md: text,
        token: session.access_token,
        requested_max_depth: requestedMaxDepth,
      });

      clearTimeout(stepTimer);
      clearTimeout(stepTimer2);
      clearTimeout(stepTimer3);

      setStep("done");
      setActiveGenerationId(result.generation_id);
      const latest = await getLatestMindMap({ knowledge_base_id: kbId, token: session.access_token });
      applyResponse(latest);
      loadVersions(session.access_token);
    } catch (e) {
      clearTimeout(stepTimer);
      clearTimeout(stepTimer2);
      clearTimeout(stepTimer3);
      setStep("failed");
      setErrorMsg(e instanceof Error ? e.message : "未知错误");
    } finally {
      setGenerating(false);
    }
  }, [inputText, inputTitle, effectiveKbId, applyResponse, loadVersions, requestedMaxDepth]);

  // Auto-trigger generation when initialText is provided
  useEffect(() => {
    if (initialText && initialText.trim().length >= 20 && !autoTriggered.current && effectiveKbId) {
      autoTriggered.current = true;
      handleGenerate();
    }
  }, [initialText, handleGenerate, effectiveKbId]);

  // Regenerate
  const handleRegenerate = useCallback(async () => {
    if (!effectiveKbId) return;

    const session = await getCloudSession();
    if (!session?.access_token) {
      setShowLoginPrompt(true);
      return;
    }

    setGenerating(true);
    setStep("preparing");
    setErrorMsg("");
    setFeedbackGiven(false);
    setAnalyticsToken(session.access_token);

    const previousGenId = activeGenerationId;

    try {
      const result = await regenerateMindMap({ knowledge_base_id: effectiveKbId, token: session.access_token, requested_max_depth: requestedMaxDepth });
      setStep("done");
      setActiveGenerationId(result.generation_id);
      trackEvent({
        event_name: "mindmap_regenerated",
        knowledge_base_id: effectiveKbId,
        generation_id: result.generation_id,
        properties: { previous_generation_id: previousGenId, requested_max_depth: requestedMaxDepth },
      });
      const latest = await getLatestMindMap({ knowledge_base_id: effectiveKbId, token: session.access_token });
      applyResponse(latest);
      loadVersions(session.access_token);
    } catch (e) {
      setStep("failed");
      setErrorMsg(e instanceof Error ? e.message : "重新生成失败");
    } finally {
      setGenerating(false);
    }
  }, [effectiveKbId, applyResponse, loadVersions, activeGenerationId, requestedMaxDepth]);

  const resetToNew = useCallback(() => {
    setCurrentData(null);
    setFlowNodes([]);
    setFlowEdges([]);
    setInputText("");
    setInputTitle("");
    setStep("idle");
    setErrorMsg("");
    autoTriggered.current = false;
  }, []);

  // Node edit (double-click)
  const handleNodeDoubleClick = useCallback(
    async (nodeId: string, newText: string) => {
      if (!currentData) return;
      const node = currentData.mind_map.nodes.find((n) => n.id === nodeId);
      if (!node || newText === node.text) return;

      const session = await getCloudSession();
      if (!session?.access_token) return;

      try {
        const result = await patchMindMap({
          mind_map_id: currentData.id,
          token: session.access_token,
          update_node: { id: nodeId, text: newText },
        });
        applyResponse(result);
        trackEvent({
          event_name: "mindmap_node_edited",
          knowledge_base_id: effectiveKbId,
          generation_id: activeGenerationId,
          mind_map_id: currentData.id,
          properties: { node_id: nodeId, before_length: node.text.length, after_length: newText.length },
        });
      } catch {
        setErrorMsg("修改节点失败");
      }
    },
    [currentData, applyResponse, effectiveKbId, activeGenerationId]
  );

  // Delete current mind map version
  const handleDeleteVersion = useCallback(async () => {
    if (!currentData?.id) return;
    if (!window.confirm("确认删除这个版本的思维导图？")) return;

    const session = await getCloudSession();
    if (!session?.access_token) return;

    try {
      await deleteMindMap({ mind_map_id: currentData.id, token: session.access_token });
      resetToNew();
      loadVersions(session.access_token);
    } catch (e) {
      setErrorMsg(e instanceof Error ? e.message : "删除失败");
    }
  }, [currentData, resetToNew, loadVersions]);

  // Download PNG
  const handleDownloadPng = useCallback(async () => {
    if (!flowCanvasRef.current) return;
    try {
      const dataUrl = await flowCanvasRef.current.exportPng();
      if (!dataUrl) {
        setErrorMsg("PNG导出失败，请重试");
        return;
      }
      const title = currentData?.mind_map.title?.trim() || "mindmap";
      const safeName = title.replace(/[<>:"/\\|?*\x00-\x1f]/g, "_");
      const link = document.createElement("a");
      link.href = dataUrl;
      link.download = `${safeName}.png`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      trackEvent({
        event_name: "mindmap_exported",
        knowledge_base_id: effectiveKbId,
        generation_id: activeGenerationId,
        mind_map_id: currentData?.id,
        properties: { format: "png" },
      });
    } catch {
      setErrorMsg("PNG导出失败，请重试");
    }
  }, [currentData, effectiveKbId, activeGenerationId]);

  // Copy JSON
  const handleCopyJson = useCallback(() => {
    if (!currentData) return;
    const json = JSON.stringify(currentData.mind_map, null, 2);
    navigator.clipboard.writeText(json).then(() => {
      setErrorMsg("");
      trackEvent({
        event_name: "mindmap_exported",
        knowledge_base_id: effectiveKbId,
        generation_id: activeGenerationId,
        mind_map_id: currentData.id,
        properties: { format: "json" },
      });
    });
  }, [currentData, effectiveKbId, activeGenerationId]);

  // Feedback handler
  const handleFeedback = useCallback((rating: "positive" | "negative", reason?: string) => {
    setFeedbackGiven(true);
    trackEvent({
      event_name: "mindmap_feedback_submitted",
      knowledge_base_id: effectiveKbId,
      generation_id: activeGenerationId,
      mind_map_id: currentData?.id,
      properties: { rating, reason: reason || null, node_count: currentData?.mind_map.nodes.length },
    });
  }, [effectiveKbId, activeGenerationId, currentData]);

  return (
    <div className="mm-page">
      {/* Login prompt modal */}
      {showLoginPrompt && (
        <div
          className="mm-login-overlay"
          style={{
            position: "fixed", top: 0, left: 0, right: 0, bottom: 0,
            display: "flex", alignItems: "center", justifyContent: "center",
            background: "rgba(23,21,19,0.5)", zIndex: 1000,
          }}
          onClick={() => setShowLoginPrompt(false)}
        >
          <div
            style={{
              background: "#fff", borderRadius: "20px", padding: "32px",
              maxWidth: "380px", width: "90%", textAlign: "center",
              boxShadow: "0 20px 60px rgba(0,0,0,0.2)",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3 style={{ margin: "0 0 12px", fontSize: "18px", color: "#171513" }}>需要登录</h3>
            <p style={{ margin: "0 0 24px", color: "#77716c", fontSize: "14px", lineHeight: "1.6" }}>
              生成思维导图需要登录账号。登录后即可使用 AI 生成功能。
            </p>
            <div style={{ display: "flex", gap: "12px", justifyContent: "center" }}>
              <button
                style={{
                  padding: "10px 24px", borderRadius: "12px", border: "none",
                  background: "#FF6A1A", color: "#fff", fontWeight: "700",
                  cursor: "pointer", fontSize: "14px",
                }}
                onClick={() => { setShowLoginPrompt(false); navigate("/"); }}
              >
                去登录
              </button>
              <button
                style={{
                  padding: "10px 24px", borderRadius: "12px", border: "1px solid #e8e0d8",
                  background: "#fff", color: "#171513", fontWeight: "500",
                  cursor: "pointer", fontSize: "14px",
                }}
                onClick={() => setShowLoginPrompt(false)}
              >
                取消
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Mobile sidebar backdrop */}
      {mobileSidebarOpen && (
        <div className="mm-mobile-backdrop visible" onClick={() => setMobileSidebarOpen(false)} />
      )}

      {/* Sidebar - Versions */}
      <aside className={`mm-sidebar ${sidebarOpen ? "" : "mm-sidebar-collapsed"} ${mobileSidebarOpen ? "mm-sidebar-mobile-open" : ""}`}>
        <div className="mm-sidebar-header">
          <button className="mm-btn-icon" onClick={() => { setSidebarOpen(!sidebarOpen); setMobileSidebarOpen(false); }}>
            {sidebarOpen ? "◁" : "▷"}
          </button>
          {sidebarOpen && <span className="mm-sidebar-title">版本记录</span>}
        </div>
        {sidebarOpen && (
          <>
            <div className="mm-sidebar-actions">
              <button className="mm-btn-new" onClick={resetToNew}>
                + 新建
              </button>
              {onBack && (
                <button className="mm-btn-back-sidebar" onClick={onBack}>
                  返回知识库
                </button>
              )}
            </div>
            <div className="mm-sidebar-list">
              {versions.map((item) => {
                const isActive = currentData?.id === item.id;
                return (
                  <div key={item.id} className={`mm-history-row ${isActive ? "active" : ""}`}>
                    <button
                      className="mm-history-item"
                      onClick={async () => {
                        if (!effectiveKbId) return;
                        const session = await getCloudSession();
                        if (!session?.access_token) return;
                        try {
                          const latest = await getLatestMindMap({ knowledge_base_id: effectiveKbId, token: session.access_token });
                          applyResponse(latest);
                          setStep("done");
                        } catch {
                          setErrorMsg("加载版本失败");
                        }
                      }}
                    >
                      <span className="mm-history-title">版本 {item.version_no}</span>
                      <span className="mm-history-meta">
                        {item.updated_at ? new Date(item.updated_at).toLocaleString(undefined, { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }) : ""}
                      </span>
                    </button>
                  </div>
                );
              })}
              {versions.length === 0 && (
                <p className="mm-empty-hint">暂无版本记录</p>
              )}
            </div>
          </>
        )}
      </aside>

      {/* Main content */}
      <main className="mm-main">
        {/* Mobile toggle for sidebar */}
        <button
          className="mm-mobile-toggle mm-btn-icon"
          style={{ position: "absolute", top: "8px", left: "8px", zIndex: 5 }}
          onClick={() => setMobileSidebarOpen(true)}
          aria-label="打开版本记录"
        >
          ☰
        </button>

        {/* Input panel - show when no result */}
        {!currentData && (
          <div className="mm-input-panel">
            {onBack && (
              <button className="mm-btn-back-top" onClick={onBack}>
                ← 返回知识库
              </button>
            )}
            <h2 className="mm-heading">思维导图生成</h2>
            <p className="mm-desc">
              粘贴长文本，AI 自动提取知识点并生成结构化思维导图。
            </p>

            <div className="mm-field">
              <label htmlFor="mm-title">标题（可选）</label>
              <input
                id="mm-title"
                type="text"
                placeholder="留空则自动提取"
                value={inputTitle}
                onChange={(e) => setInputTitle(e.target.value)}
                maxLength={120}
              />
            </div>

            <div className="mm-field">
              <label htmlFor="mm-text">文本内容</label>
              <textarea
                id="mm-text"
                placeholder="在此粘贴课程笔记、会议记录、学习资料等长文本..."
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                rows={12}
              />
              <span className="mm-char-count">{inputText.length} 字</span>
            </div>

            {/* Status */}
            {step !== "idle" && step !== "done" && (
              <div className={`mm-status ${step === "failed" ? "mm-status-error" : ""}`}>
                {step !== "failed" && <span className="mm-spinner" />}
                {STEP_LABELS[step]}
              </div>
            )}
            {errorMsg && <div className="mm-status mm-status-error">{errorMsg}</div>}

            <div className="mm-depth-selector" style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "12px" }}>
              <label style={{ fontSize: "13px", color: "#4A4541", whiteSpace: "nowrap" }}>最大层数</label>
              <select
                value={requestedMaxDepth}
                onChange={(e) => setRequestedMaxDepth(Number(e.target.value))}
                style={{
                  padding: "6px 12px",
                  fontSize: "13px",
                  borderRadius: "8px",
                  border: "1px solid #E0D6CF",
                  background: "#FFFCF9",
                  color: "#171513",
                  cursor: "pointer",
                  minHeight: "40px",
                }}
              >
                <option value={3}>3 层</option>
                <option value={4}>4 层</option>
                <option value={5}>5 层</option>
                <option value={6}>6 层</option>
              </select>
            </div>

            <button
              className="mm-btn-generate"
              onClick={handleGenerate}
              disabled={generating || !inputText.trim()}
            >
              {generating ? "生成中..." : "生成思维导图"}
            </button>
          </div>
        )}

        {/* Canvas panel - show when result exists */}
        {currentData && (
          <div className="mm-canvas-panel">
            <div className="mm-toolbar">
              <h3 className="mm-canvas-title">{currentData.mind_map.title}</h3>
              <div className="mm-toolbar-actions">
                <button className="mm-btn-regen" onClick={() => {
                  if (window.confirm("确认重新生成？将创建新版本。")) handleRegenerate();
                }} disabled={generating}>
                  重新生成
                </button>
                <button onClick={handleDownloadPng}>下载 PNG</button>
                <button onClick={handleCopyJson}>复制 JSON</button>
                <button onClick={handleDeleteVersion}>删除版本</button>
                <button onClick={resetToNew}>新建</button>
                {onBack && <button onClick={onBack}>返回</button>}
              </div>
            </div>

            {step !== "idle" && step !== "done" && (
              <div className="mm-status mm-status-overlay">
                <span className="mm-spinner" />
                {STEP_LABELS[step]}
              </div>
            )}

            <div className="mm-canvas">
              <ReactFlowProvider>
                <FlowCanvas
                  ref={flowCanvasRef}
                  flowNodes={flowNodes}
                  flowEdges={flowEdges}
                  onNodeDoubleClick={handleNodeDoubleClick}
                />
              </ReactFlowProvider>
            </div>

            {/* Feedback UI */}
            {step === "done" && !feedbackGiven && (
              <div className="mm-feedback" style={{ display: "flex", alignItems: "center", gap: "12px", padding: "8px 16px" }}>
                <span style={{ fontSize: "13px", color: "#77716c" }}>这个导图对你有帮助吗？</span>
                <button
                  className="mm-feedback-btn"
                  style={{ border: "none", background: "none", cursor: "pointer", fontSize: "20px" }}
                  onClick={() => handleFeedback("positive")}
                  aria-label="有帮助"
                >👍</button>
                <button
                  className="mm-feedback-btn"
                  style={{ border: "none", background: "none", cursor: "pointer", fontSize: "20px" }}
                  onClick={() => {
                    const reasons = ["missing_content", "wrong_hierarchy", "redundant_content", "unclear_expression", "poor_structure", "other"];
                    const labels = ["内容缺失", "层级错误", "内容冗余", "表达不清", "结构不佳", "其他"];
                    const idx = reasons.findIndex((_, i) => window.confirm(`是否因为「${labels[i]}」？\n（取消可选下一个原因）`));
                    handleFeedback("negative", idx >= 0 ? reasons[idx] : undefined);
                  }}
                  aria-label="没帮助"
                >👎</button>
              </div>
            )}
            {feedbackGiven && (
              <div style={{ padding: "8px 16px", fontSize: "13px", color: "#77716c" }}>感谢反馈！</div>
            )}

            <p className="mm-hint">双击节点可编辑内容 · 版本 {currentData.version_no}</p>
          </div>
        )}
      </main>
    </div>
  );
}
