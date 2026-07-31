/**
 * Mind Map page - V0 refactored implementation
 * Uses @xyflow/react for rendering, communicates with new /api/mindmaps endpoints
 */

import { useCallback, useEffect, useRef, useState } from "react";
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
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { toPng } from "html-to-image";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

// --- Types ---
interface RenderNode {
  id: string;
  parent_id: string | null;
  text: string;
  level: number;
  order: number;
  side: string | null;
  source_ids: string[];
  x: number;
  y: number;
  width: number;
  height: number;
}

interface RenderEdge {
  id: string;
  source: string;
  target: string;
}

interface ValidationResult {
  passed: boolean;
  score: number;
  errors: Array<{ code: string; message: string; node_id?: string }>;
  warnings: Array<{ code: string; message: string; node_id?: string }>;
  retry_count: number;
}

interface MindMapResponse {
  task_id: string;
  status: string;
  title: string;
  nodes: RenderNode[];
  edges: RenderEdge[];
  validation: ValidationResult | null;
  created_at: string;
}

interface HistoryItem {
  task_id: string;
  title: string;
  status: string;
  node_count: number;
  created_at: string;
  updated_at: string;
}

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

// --- API Calls ---
async function apiGenerate(body: {
  text: string;
  title?: string;
  max_depth: number;
  source_only: boolean;
  map_type: string;
}): Promise<MindMapResponse> {
  const res = await fetch(`${API_BASE}/api/mindmaps/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `生成失败 (HTTP ${res.status})`);
  }
  return res.json();
}

async function apiGetMindmap(taskId: string): Promise<MindMapResponse> {
  const res = await fetch(`${API_BASE}/api/mindmaps/${taskId}`);
  if (!res.ok) throw new Error("获取导图失败");
  return res.json();
}

async function apiRegenerate(
  taskId: string,
  body: { max_depth: number; map_type: string }
): Promise<MindMapResponse> {
  const res = await fetch(`${API_BASE}/api/mindmaps/${taskId}/regenerate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error("重新生成失败");
  return res.json();
}

async function apiPatch(
  taskId: string,
  body: Record<string, unknown>
): Promise<MindMapResponse> {
  const res = await fetch(`${API_BASE}/api/mindmaps/${taskId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error("修改失败");
  return res.json();
}

async function apiListHistory(): Promise<HistoryItem[]> {
  const res = await fetch(`${API_BASE}/api/mindmaps`);
  if (!res.ok) return [];
  return res.json();
}

// --- Helpers ---
function responseToFlow(data: MindMapResponse): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = data.nodes.map((n) => {
    let sourcePosition = Position.Right;
    let targetPosition = Position.Left;

    if (n.level === 0) {
      sourcePosition = Position.Right;
      targetPosition = Position.Left;
    } else if (n.side === "left") {
      sourcePosition = Position.Left;
      targetPosition = Position.Right;
    } else {
      sourcePosition = Position.Right;
      targetPosition = Position.Left;
    }

    return {
      id: n.id,
      position: { x: n.x, y: n.y },
      data: { label: n.text, level: n.level, side: n.side },
      type: "default",
      sourcePosition,
      targetPosition,
      style: {
        width: n.width,
        minHeight: n.height,
        background: n.level === 0 ? "#22c55e" : n.level === 1 ? "#f3f4f6" : "#fafafa",
        color: n.level === 0 ? "#fff" : "#1f2937",
        border: n.level === 0 ? "2px solid #16a34a" : "1px solid #e5e7eb",
        borderRadius: n.level === 0 ? "12px" : "8px",
        padding: "10px 14px",
        fontSize: n.level === 0 ? "15px" : "13px",
        fontWeight: n.level === 0 ? "700" : n.level === 1 ? "600" : "400",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        textAlign: "center" as const,
        lineHeight: "1.4",
        boxShadow: n.level === 0 ? "0 2px 8px rgba(34,197,94,0.2)" : "0 1px 3px rgba(0,0,0,0.06)",
      },
    };
  });

  const edges: Edge[] = data.edges.map((e) => {
    return {
      id: e.id,
      source: e.source,
      target: e.target,
      type: "smoothstep",
      style: { stroke: "#d1d5db", strokeWidth: 1.5 },
      markerEnd: { type: MarkerType.ArrowClosed, color: "#d1d5db", width: 12, height: 12 },
    };
  });

  return { nodes, edges };
}

// --- Flow Inner Component ---
function FlowCanvas({
  flowNodes,
  flowEdges,
  onNodeDoubleClick,
}: {
  flowNodes: Node[];
  flowEdges: Edge[];
  onNodeDoubleClick: (id: string) => void;
}) {
  const [nodes, setNodes, onNodesChange] = useNodesState(flowNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(flowEdges);
  const { fitView } = useReactFlow();

  useEffect(() => {
    setNodes(flowNodes);
    setEdges(flowEdges);
    setTimeout(() => fitView({ padding: 0.2 }), 50);
  }, [flowNodes, flowEdges, setNodes, setEdges, fitView]);

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      onNodeDoubleClick={(_, node) => onNodeDoubleClick(node.id)}
      fitView
      minZoom={0.15}
      maxZoom={2}
      proOptions={{ hideAttribution: true }}
    >
      <Background gap={20} color="#f0f0f0" />
      <Controls showInteractive={false} />
      <MiniMap
        pannable
        zoomable
        style={{ background: "#fafafa", border: "1px solid #e5e7eb" }}
      />
    </ReactFlow>
  );
}

// --- Main Page Component ---
export default function MindMapPage({ onBack, initialText, taskId }: { onBack?: () => void; initialText?: string; taskId?: string }) {
  const navigate = useNavigate();
  const [inputText, setInputText] = useState(initialText || "");
  const [inputTitle, setInputTitle] = useState("");
  const [maxDepth, setMaxDepth] = useState(4);
  const [sourceOnly, setSourceOnly] = useState(true);
  const [mapType, setMapType] = useState<"auto" | "knowledge" | "process">("auto");

  const [currentData, setCurrentData] = useState<MindMapResponse | null>(null);
  const [flowNodes, setFlowNodes] = useState<Node[]>([]);
  const [flowEdges, setFlowEdges] = useState<Edge[]>([]);

  const [step, setStep] = useState<GenerationStep>("idle");
  const [errorMsg, setErrorMsg] = useState("");
  const [generating, setGenerating] = useState(false);

  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  const canvasRef = useRef<HTMLDivElement>(null);
  const autoTriggered = useRef(false);

  // Load history on mount
  useEffect(() => {
    apiListHistory().then(setHistory).catch(() => {});
  }, []);

  // Load from taskId (URL-based restore)
  useEffect(() => {
    if (taskId && !currentData) {
      apiGetMindmap(taskId)
        .then((result) => {
          applyResponse(result);
          setStep("done");
        })
        .catch(() => {
          setErrorMsg("导图不存在或加载失败");
        });
    }
  }, [taskId]);

  const refreshHistory = useCallback(() => {
    apiListHistory().then(setHistory).catch(() => {});
  }, []);

  // Apply response to canvas
  const applyResponse = useCallback((data: MindMapResponse) => {
    setCurrentData(data);
    const { nodes, edges } = responseToFlow(data);
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

    setGenerating(true);
    setErrorMsg("");
    setStep("preparing");

    // Simulate step progression for UX
    const stepTimer = setTimeout(() => setStep("extracting"), 800);
    const stepTimer2 = setTimeout(() => setStep("validating"), 2500);
    const stepTimer3 = setTimeout(() => setStep("rendering"), 4000);

    try {
      const result = await apiGenerate({
        text,
        title: inputTitle.trim() || undefined,
        max_depth: maxDepth,
        source_only: sourceOnly,
        map_type: mapType,
      });

      clearTimeout(stepTimer);
      clearTimeout(stepTimer2);
      clearTimeout(stepTimer3);

      if (result.status === "failed") {
        setStep("failed");
        setErrorMsg("生成失败，请重试");
      } else {
        setStep("done");
        applyResponse(result);
        refreshHistory();
        navigate(`/mindmap/${result.task_id}`, { replace: true });
      }
    } catch (e) {
      clearTimeout(stepTimer);
      clearTimeout(stepTimer2);
      clearTimeout(stepTimer3);
      setStep("failed");
      setErrorMsg(e instanceof Error ? e.message : "未知错误");
    } finally {
      setGenerating(false);
    }
  }, [inputText, inputTitle, maxDepth, sourceOnly, mapType, applyResponse, refreshHistory, navigate]);

  // Auto-trigger generation when initialText is provided
  useEffect(() => {
    if (initialText && initialText.trim().length >= 20 && !autoTriggered.current) {
      autoTriggered.current = true;
      handleGenerate();
    }
  }, [initialText, handleGenerate]);

  // Regenerate
  const handleRegenerate = useCallback(async () => {
    if (!currentData) return;
    setGenerating(true);
    setStep("preparing");
    setErrorMsg("");
    try {
      const result = await apiRegenerate(currentData.task_id, {
        max_depth: maxDepth,
        map_type: mapType,
      });
      setStep("done");
      applyResponse(result);
      refreshHistory();
      navigate(`/mindmap/${result.task_id}`, { replace: true });
    } catch (e) {
      setStep("failed");
      setErrorMsg(e instanceof Error ? e.message : "重新生成失败");
    } finally {
      setGenerating(false);
    }
  }, [currentData, maxDepth, mapType, applyResponse, refreshHistory, navigate]);

  // Load from history - navigate to URL
  const handleLoadHistory = useCallback(
    (taskId: string) => {
      navigate(`/mindmap/${taskId}`);
    },
    [navigate]
  );

  // Node edit (double-click)
  const handleNodeDoubleClick = useCallback(
    async (nodeId: string) => {
      if (!currentData) return;
      const node = currentData.nodes.find((n) => n.id === nodeId);
      if (!node) return;
      const newText = prompt("编辑节点内容", node.text);
      if (!newText?.trim() || newText.trim() === node.text) return;
      try {
        const result = await apiPatch(currentData.task_id, {
          update_node: { id: nodeId, text: newText.trim() },
        });
        applyResponse(result);
      } catch {
        setErrorMsg("修改节点失败");
      }
    },
    [currentData, applyResponse]
  );

  // Download PNG
  const handleDownloadPng = useCallback(async () => {
    const el = canvasRef.current?.querySelector(".react-flow") as HTMLElement;
    if (!el) return;
    try {
      const dataUrl = await toPng(el, {
        backgroundColor: "#ffffff",
        pixelRatio: 2,
      });
      const a = document.createElement("a");
      a.href = dataUrl;
      a.download = `${currentData?.title || "mindmap"}.png`;
      a.click();
    } catch {
      setErrorMsg("PNG导出失败，请重试");
    }
  }, [currentData]);

  // Copy JSON
  const handleCopyJson = useCallback(() => {
    if (!currentData) return;
    const json = JSON.stringify(
      { title: currentData.title, nodes: currentData.nodes, edges: currentData.edges },
      null,
      2
    );
    navigator.clipboard.writeText(json).then(() => {
      setErrorMsg("");
    });
  }, [currentData]);

  return (
    <div className="mm-page">
      {/* Sidebar - History */}
      <aside className={`mm-sidebar ${sidebarOpen ? "" : "mm-sidebar-collapsed"}`}>
        <div className="mm-sidebar-header">
          <button className="mm-btn-icon" onClick={() => setSidebarOpen(!sidebarOpen)}>
            {sidebarOpen ? "◁" : "▷"}
          </button>
          {sidebarOpen && <span className="mm-sidebar-title">历史记录</span>}
        </div>
        {sidebarOpen && (
          <div className="mm-sidebar-list">
            <button
              className="mm-btn-new"
              onClick={() => {
                setCurrentData(null);
                setFlowNodes([]);
                setFlowEdges([]);
                setStep("idle");
                setErrorMsg("");
              }}
            >
              + 新建
            </button>
            {history.map((item) => (
              <button
                key={item.task_id}
                className={`mm-history-item ${
                  currentData?.task_id === item.task_id ? "active" : ""
                }`}
                onClick={() => handleLoadHistory(item.task_id)}
              >
                <span className="mm-history-title">{item.title}</span>
                <span className="mm-history-meta">
                  {item.node_count}节点 · {new Date(item.created_at).toLocaleDateString()}
                </span>
              </button>
            ))}
            {history.length === 0 && (
              <p className="mm-empty-hint">暂无历史记录</p>
            )}
          </div>
        )}
      </aside>

      {/* Main content */}
      <main className="mm-main">
        {/* Input panel - show when no result */}
        {!currentData && (
          <div className="mm-input-panel">
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

            <div className="mm-options">
              <div className="mm-option">
                <label htmlFor="mm-depth">最大层级</label>
                <select
                  id="mm-depth"
                  value={maxDepth}
                  onChange={(e) => setMaxDepth(Number(e.target.value))}
                >
                  <option value={2}>2</option>
                  <option value={3}>3</option>
                  <option value={4}>4</option>
                  <option value={5}>5</option>
                  <option value={6}>6</option>
                </select>
              </div>
              <div className="mm-option">
                <label htmlFor="mm-type">类型</label>
                <select
                  id="mm-type"
                  value={mapType}
                  onChange={(e) =>
                    setMapType(e.target.value as "auto" | "knowledge" | "process")
                  }
                >
                  <option value="auto">自动</option>
                  <option value="knowledge">知识型</option>
                  <option value="process">流程型</option>
                </select>
              </div>
              <div className="mm-option mm-checkbox">
                <input
                  id="mm-source"
                  type="checkbox"
                  checked={sourceOnly}
                  onChange={(e) => setSourceOnly(e.target.checked)}
                />
                <label htmlFor="mm-source">仅依据原文</label>
              </div>
            </div>

            {/* Status */}
            {step !== "idle" && step !== "done" && (
              <div className={`mm-status ${step === "failed" ? "mm-status-error" : ""}`}>
                {step !== "failed" && <span className="mm-spinner" />}
                {STEP_LABELS[step]}
              </div>
            )}
            {errorMsg && <div className="mm-status mm-status-error">{errorMsg}</div>}

            <button
              className="mm-btn-generate"
              onClick={handleGenerate}
              disabled={generating || !inputText.trim()}
            >
              {generating ? "生成中..." : "生成思维导图"}
            </button>

            {onBack && (
              <button className="mm-btn-back" onClick={onBack}>
                ← 返回知识库
              </button>
            )}
          </div>
        )}

        {/* Canvas panel - show when result exists */}
        {currentData && (
          <div className="mm-canvas-panel">
            <div className="mm-toolbar">
              <h3 className="mm-canvas-title">{currentData.title}</h3>
              <div className="mm-toolbar-actions">
                <button onClick={handleRegenerate} disabled={generating}>
                  重新生成
                </button>
                <button onClick={handleDownloadPng}>下载 PNG</button>
                <button onClick={handleCopyJson}>复制 JSON</button>
                <button
                  onClick={() => {
                    setCurrentData(null);
                    setFlowNodes([]);
                    setFlowEdges([]);
                    setStep("idle");
                  }}
                >
                  新建
                </button>
                {onBack && <button onClick={onBack}>返回</button>}
              </div>
            </div>

            {step !== "idle" && step !== "done" && (
              <div className="mm-status mm-status-overlay">
                <span className="mm-spinner" />
                {STEP_LABELS[step]}
              </div>
            )}

            {currentData.validation && !currentData.validation.passed && (
              <div className="mm-validation-warn">
                校验分数: {currentData.validation.score}/100
                {currentData.validation.errors.length > 0 &&
                  ` · ${currentData.validation.errors.length} 个错误`}
              </div>
            )}

            <div className="mm-canvas" ref={canvasRef}>
              <ReactFlowProvider>
                <FlowCanvas
                  flowNodes={flowNodes}
                  flowEdges={flowEdges}
                  onNodeDoubleClick={handleNodeDoubleClick}
                />
              </ReactFlowProvider>
            </div>

            <p className="mm-hint">双击节点可编辑内容</p>
          </div>
        )}
      </main>
    </div>
  );
}
