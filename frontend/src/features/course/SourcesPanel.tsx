import { useState } from "react";
import { FileText, FileImage, Presentation, Plus, X, Check, AlertTriangle, ChevronDown, ChevronRight, Loader2, RefreshCw, FileText as FileTextIcon } from "lucide-react";
import { Button } from "../../components/ui/Button";
import { Checkbox } from "../../components/ui/Checkbox";
import { Badge } from "../../components/ui/Badge";
import { Tooltip } from "../../components/ui/Tooltip";
import { Spinner } from "../../components/ui/Spinner";
import { useMaterials } from "./useMaterials";
import { useNotes } from "./useNotes";
import MaterialUpload from "./MaterialUpload";
import type {
  KnowledgeStatus,
  Material,
  MaterialEvidenceState,
  MaterialEvidenceStatus,
  PersistedKnowledgeJobStatus,
  ProjectionStatus,
  SourceEvidenceStatus,
} from "../../shared/types";

interface SourcesPanelProps {
  courseId: string;
  collapsed: boolean;
  selectedSourceIds: string[];
  selectedNoteIds: string[];
  onSelectionChange: (sourceIds: string[], noteIds: string[]) => void;
  knowledgeStatus: KnowledgeStatus | null;
  knowledgeStatusLoading: boolean;
  knowledgeStatusError: string | null;
  knowledgeStatusAutoRefreshPaused: boolean;
  onRefreshKnowledgeStatus: () => Promise<KnowledgeStatus | null>;
}

function MaterialIcon({ kind }: { kind: string }) {
  switch (kind) {
    case "pdf":
      return <FileText className="w-4 h-4 text-red-500 shrink-0" />;
    case "ppt":
      return <Presentation className="w-4 h-4 text-orange-500 shrink-0" />;
    case "image":
      return <FileImage className="w-4 h-4 text-emerald-500 shrink-0" />;
    case "text_note":
      return <FileTextIcon className="w-4 h-4 text-blue-500 shrink-0" />;
    default:
      return <FileText className="w-4 h-4 text-slate-500 shrink-0" />;
  }
}

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.(pdf|pptx?|txt|md)$/i;

const KIND_LABELS: Record<string, string> = {
  pdf: "PDF 文档",
  ppt: "PPT 课件",
  text_note: "文本笔记",
  image: "图片",
};

function formatMaterialName(filename: string, kind: string, index: number): string {
  if (UUID_PATTERN.test(filename)) {
    const label = KIND_LABELS[kind] || "材料";
    return `${label} ${index + 1}`;
  }
  return filename;
}

const MATERIAL_EVIDENCE_LABEL: Record<MaterialEvidenceState, string> = {
  processing: "正在建立证据",
  ready: "证据就绪",
  retryable: "等待重试",
  failed: "证据处理失败",
  missing_evidence: "缺少可用证据",
};

const MATERIAL_EVIDENCE_VARIANT: Record<
  MaterialEvidenceState,
  "success" | "warning" | "error" | "info"
> = {
  processing: "info",
  ready: "success",
  retryable: "warning",
  failed: "error",
  missing_evidence: "error",
};

const JOB_STATUS_LABEL: Record<PersistedKnowledgeJobStatus, string> = {
  queued: "已入队",
  running: "处理中",
  succeeded: "已完成",
  retryable: "可重试",
  failed: "失败",
};

const SOURCE_STATUS_LABEL: Record<SourceEvidenceStatus, string> = {
  empty: "尚无证据",
  processing: "建立证据中",
  partial: "部分证据就绪",
  ready: "材料证据就绪",
  failed: "证据不可用",
};

const SOURCE_STATUS_VARIANT: Record<
  SourceEvidenceStatus,
  "default" | "info" | "warning" | "success" | "error"
> = {
  empty: "default",
  processing: "info",
  partial: "warning",
  ready: "success",
  failed: "error",
};

const PROJECTION_STATUS_LABEL: Record<ProjectionStatus, string> = {
  not_started: "课程地图尚未编译",
  processing: "课程地图编译中",
  ready: "课程地图已编译",
  stale: "课程地图需要重编译",
  failed: "课程地图编译失败",
};

function MaterialEvidenceIcon({ status }: { status: MaterialEvidenceState | undefined }) {
  if (status === "processing") {
    return <Loader2 className="w-3.5 h-3.5 text-foxAmber animate-spin shrink-0" />;
  }
  if (status === "ready") {
    return <Check className="w-3.5 h-3.5 text-emerald-500 shrink-0" />;
  }
  if (status === "retryable") {
    return <AlertTriangle className="w-3.5 h-3.5 text-amber-500 shrink-0" />;
  }
  if (status === "failed" || status === "missing_evidence") {
    return <AlertTriangle className="w-3.5 h-3.5 text-red-500 shrink-0" />;
  }
  return <span className="w-2 h-2 rounded-full bg-slate-300 shrink-0" title="证据状态待读取" />;
}

function MaterialEvidenceDetails({
  evidence,
  statusError,
}: {
  evidence: MaterialEvidenceStatus | undefined;
  statusError: string | null;
}) {
  if (statusError) {
    return (
      <div className="mt-2 ml-6 rounded-lg border border-red-100 bg-red-50 px-2.5 py-2 text-xs text-red-600" role="alert">
        无法读取 V2 证据状态：{statusError}
      </div>
    );
  }

  if (!evidence) {
    return (
      <div className="mt-2 ml-6 rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-2 text-xs text-slate-500">
        当前材料尚未出现在证据快照中，等待状态刷新。
      </div>
    );
  }

  return (
    <div className="mt-2 ml-6 rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-2 space-y-1.5 text-xs text-slate-600">
      <div className="flex items-center justify-between gap-2">
        <Badge variant={MATERIAL_EVIDENCE_VARIANT[evidence.status]} size="sm">
          {MATERIAL_EVIDENCE_LABEL[evidence.status]}
        </Badge>
        <span>revision {evidence.material_revision}</span>
      </div>
      <p>{evidence.fragment_count} 个可定位证据片段</p>
      {evidence.job_status && <p>持久任务：{JOB_STATUS_LABEL[evidence.job_status]}</p>}
      {evidence.error_code && (
        <div className="rounded-md bg-red-50 px-2 py-1.5 text-red-600" role="alert">
          <p className="font-medium">{evidence.error_code}</p>
          {evidence.error_detail && <p className="mt-0.5 leading-relaxed">{evidence.error_detail}</p>}
        </div>
      )}
    </div>
  );
}

function sourceSummary(snapshot: KnowledgeStatus): string {
  const { coverage } = snapshot;
  switch (snapshot.source_status) {
    case "empty":
      return "尚未有材料进入可检索证据库。";
    case "processing":
      return "正在将材料转换为可定位的课程证据。";
    case "partial":
      return `已有 ${coverage.ready_materials}/${coverage.total_materials} 份材料可作为证据，其余材料仍需处理或重试。`;
    case "ready":
      return `${coverage.ready_materials} 份材料已形成可定位证据。`;
    case "failed":
      return "当前没有可用于 V2 检索的材料证据，请查看具体材料错误。";
  }
}

function KnowledgeEvidenceSummary({
  snapshot,
  loading,
  error,
  autoRefreshPaused,
  onRefresh,
}: {
  snapshot: KnowledgeStatus | null;
  loading: boolean;
  error: string | null;
  autoRefreshPaused: boolean;
  onRefresh: () => Promise<KnowledgeStatus | null>;
}) {
  if (!snapshot && loading) {
    return (
      <div className="mx-3 mt-3 flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs text-slate-500">
        <Spinner size="sm" />
        正在读取材料证据状态…
      </div>
    );
  }

  if (!snapshot && error) {
    return (
      <div className="mx-3 mt-3 rounded-lg border border-red-100 bg-red-50 px-3 py-2 text-xs text-red-600" role="alert">
        <div className="flex items-start justify-between gap-2">
          <span>材料证据状态读取失败：{error}</span>
          <button
            type="button"
            onClick={() => { void onRefresh(); }}
            className="shrink-0 underline hover:text-red-700"
          >
            重试
          </button>
        </div>
      </div>
    );
  }

  if (!snapshot) return null;

  const { coverage } = snapshot;
  const sourceReadyWithoutProjection =
    snapshot.source_status === "ready" &&
    snapshot.status === "partial" &&
    snapshot.projection_status === "not_started";

  return (
    <section className="mx-3 mt-3 rounded-lg border border-slate-200 bg-white p-3" aria-label="课程材料证据状态">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-xs font-semibold text-slate-700">材料证据</span>
          <Badge variant={SOURCE_STATUS_VARIANT[snapshot.source_status]} size="sm" className="shrink-0">
            {SOURCE_STATUS_LABEL[snapshot.source_status]}
          </Badge>
        </div>
        <button
          type="button"
          onClick={() => { void onRefresh(); }}
          className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
          title="刷新材料证据状态"
          aria-label="刷新材料证据状态"
        >
          {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
        </button>
      </div>
      <p className="mt-2 text-xs leading-relaxed text-slate-600">{sourceSummary(snapshot)}</p>
      <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-xs text-slate-500">
        <span>已就绪 {coverage.ready_materials}/{coverage.total_materials}</span>
        <span>{coverage.fragment_count} 个片段</span>
        {coverage.processing_materials > 0 && <span>处理中 {coverage.processing_materials}</span>}
        {coverage.retryable_materials > 0 && <span>待重试 {coverage.retryable_materials}</span>}
        {coverage.failed_materials > 0 && <span className="text-red-500">异常 {coverage.failed_materials}</span>}
      </div>
      {autoRefreshPaused && coverage.processing_materials > 0 && (
        <p className="mt-2 rounded-md bg-amber-50 px-2 py-1.5 text-xs leading-relaxed text-amber-700" role="status">
          自动刷新已暂停，可手动刷新。
        </p>
      )}
      {sourceReadyWithoutProjection ? (
        <p className="mt-2 rounded-md bg-amber-50 px-2 py-1.5 text-xs leading-relaxed text-amber-700">
          材料证据已就绪，课程地图尚未编译；现在可以按材料证据追溯，课程结构仍在后续阶段生成。
        </p>
      ) : (
        <p className="mt-2 text-xs text-slate-500">{PROJECTION_STATUS_LABEL[snapshot.projection_status]}</p>
      )}
      {error && (
        <p className="mt-2 text-xs text-red-600" role="alert">
          最近一次状态刷新失败：{error}
        </p>
      )}
    </section>
  );
}

export default function SourcesPanel({
  courseId,
  collapsed,
  selectedSourceIds,
  selectedNoteIds,
  onSelectionChange,
  knowledgeStatus,
  knowledgeStatusLoading,
  knowledgeStatusError,
  knowledgeStatusAutoRefreshPaused,
  onRefreshKnowledgeStatus,
}: SourcesPanelProps) {
  const { materials, refetch: refetchMaterials } = useMaterials(courseId);
  const { notes, deleteNote } = useNotes(courseId);
  const [showUpload, setShowUpload] = useState(false);
  const [expandedMaterial, setExpandedMaterial] = useState<string | null>(null);

  const allSourceIds = materials.map((m) => m.id);
  const allSelected = materials.length > 0 && selectedSourceIds.length === allSourceIds.length;
  const evidenceByMaterialId = new Map(
    knowledgeStatus?.materials.map((evidence) => [evidence.material_id, evidence] as const) ?? [],
  );

  const toggleSelectAll = () => {
    if (allSelected) {
      onSelectionChange([], selectedNoteIds);
    } else {
      onSelectionChange(allSourceIds, selectedNoteIds);
    }
  };

  const toggleSource = (id: string) => {
    if (selectedSourceIds.includes(id)) {
      onSelectionChange(selectedSourceIds.filter((s) => s !== id), selectedNoteIds);
    } else {
      onSelectionChange([...selectedSourceIds, id], selectedNoteIds);
    }
  };

  const toggleNote = (id: string) => {
    if (selectedNoteIds.includes(id)) {
      onSelectionChange(selectedSourceIds, selectedNoteIds.filter((n) => n !== id));
    } else {
      onSelectionChange(selectedSourceIds, [...selectedNoteIds, id]);
    }
  };

  const handleDeleteMaterial = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    // TODO: implement delete material API
    onSelectionChange(selectedSourceIds.filter((s) => s !== id), selectedNoteIds);
  };

  const handleDeleteNote = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    try {
      await deleteNote(id);
      onSelectionChange(selectedSourceIds, selectedNoteIds.filter((n) => n !== id));
    } catch { /* ignore */ }
  };

  const handleUploaded = () => {
    void refetchMaterials();
    void onRefreshKnowledgeStatus();
    setShowUpload(false);
  };

  if (collapsed) {
    return (
      <div className="flex flex-col items-center py-3 gap-2">
        <Tooltip content="来源" position="right">
          <button className="p-2 rounded-lg hover:bg-slate-200 text-slate-600 transition-colors">
            <FileText className="w-5 h-5" />
          </button>
        </Tooltip>
        <Tooltip content="添加材料" position="right">
          <button
            onClick={() => setShowUpload(!showUpload)}
            className="p-2 rounded-lg hover:bg-slate-200 text-slate-600 transition-colors"
          >
            <Plus className="w-5 h-5" />
          </button>
        </Tooltip>
        <Tooltip content={allSelected ? "取消全选" : "全选"} position="right">
          <button
            onClick={toggleSelectAll}
            className={`p-2 rounded-lg transition-colors ${allSelected ? "bg-foxAmber/20 text-foxAmber" : "hover:bg-slate-200 text-slate-600"}`}
          >
            <Check className="w-5 h-5" />
          </button>
        </Tooltip>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <div className="h-12 px-3 flex items-center justify-between border-b border-slate-200 shrink-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-slate-700">来源</span>
          <Badge variant="default" className="text-xs">{materials.length}</Badge>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setShowUpload(!showUpload)}
          className="h-7 px-2"
        >
          <Plus className="w-4 h-4" />
          添加
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {showUpload && (
          <div className="p-3 border-b border-slate-200">
            <MaterialUpload courseId={courseId} onUploaded={handleUploaded} />
          </div>
        )}

        <KnowledgeEvidenceSummary
          snapshot={knowledgeStatus}
          loading={knowledgeStatusLoading}
          error={knowledgeStatusError}
          autoRefreshPaused={knowledgeStatusAutoRefreshPaused}
          onRefresh={onRefreshKnowledgeStatus}
        />

        <div className="p-3">
          {materials.length > 0 && (
            <div className="flex items-center gap-2 mb-2 px-1">
              <Checkbox checked={allSelected} onChange={toggleSelectAll} />
              <span className="text-xs text-slate-600">全选</span>
            </div>
          )}

          <div className="space-y-1">
            {materials.map((m: Material, index: number) => {
              const isSelected = selectedSourceIds.includes(m.id);
              const isExpanded = expandedMaterial === m.id;
              const evidence = evidenceByMaterialId.get(m.id);
              return (
                <div key={m.id}>
                  <div
                    className={`flex items-center gap-2 px-2 py-2 rounded-lg transition-colors group cursor-pointer ${
                      isSelected ? "bg-white" : "hover:bg-white/60"
                    }`}
                  >
                    <Checkbox checked={isSelected} onChange={() => toggleSource(m.id)} />
                    <button
                      onClick={() => setExpandedMaterial(isExpanded ? null : m.id)}
                      className="flex items-center gap-2 flex-1 min-w-0"
                    >
                      <MaterialIcon kind={m.kind} />
                      <span className="text-xs text-slate-700 truncate flex-1 text-left">
                        {formatMaterialName(m.filename, m.kind, index)}
                      </span>
                      <MaterialEvidenceIcon status={evidence?.status} />
                      {isExpanded ? (
                        <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
                      ) : (
                        <ChevronRight className="w-3.5 h-3.5 text-slate-400 opacity-0 group-hover:opacity-100" />
                      )}
                    </button>
                    <button
                      onClick={(e) => handleDeleteMaterial(e, m.id)}
                      className="p-1 rounded opacity-0 group-hover:opacity-100 hover:bg-red-50 text-red-400 hover:text-red-600 transition-all"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </div>
                  {isExpanded && (
                    <MaterialEvidenceDetails evidence={evidence} statusError={knowledgeStatusError} />
                  )}
                </div>
              );
            })}
          </div>

          {materials.length === 0 && !showUpload && (
            <div className="text-center py-6 text-slate-400">
              <FileText className="w-8 h-8 mx-auto mb-2 opacity-50" />
              <p className="text-xs">暂无材料，点击"+ 添加"上传</p>
            </div>
          )}
        </div>

        <div className="border-t border-slate-200 p-3">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold text-slate-700">笔记</span>
              <Badge variant="default" className="text-xs">{notes.length}</Badge>
            </div>
          </div>

          <div className="space-y-1">
            {notes.map((n) => {
              const isSelected = selectedNoteIds.includes(n.id);
              return (
                <div
                  key={n.id}
                  className={`flex items-center gap-2 px-2 py-2 rounded-lg transition-colors group cursor-pointer ${
                    isSelected ? "bg-white" : "hover:bg-white/60"
                  }`}
                >
                  <Checkbox checked={isSelected} onChange={() => toggleNote(n.id)} />
                  <FileTextIcon className="w-4 h-4 text-foxAmber shrink-0" />
                  <span className="text-xs text-slate-700 truncate flex-1">{n.title}</span>
                  <button
                    onClick={(e) => handleDeleteNote(e, n.id)}
                    className="p-1 rounded opacity-0 group-hover:opacity-100 hover:bg-red-50 text-red-400 hover:text-red-600 transition-all"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>
              );
            })}
            {notes.length === 0 && (
              <p className="text-xs text-slate-400 text-center py-3">暂无笔记</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
