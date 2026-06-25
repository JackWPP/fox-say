import { useState } from "react";
import { FileText, FileImage, Presentation, Plus, X, Check, AlertTriangle, ChevronDown, ChevronRight, Loader2, FileText as FileTextIcon } from "lucide-react";
import { Button } from "../../components/ui/Button";
import { Checkbox } from "../../components/ui/Checkbox";
import { Badge } from "../../components/ui/Badge";
import { Tooltip } from "../../components/ui/Tooltip";
import { Spinner } from "../../components/ui/Spinner";
import { useMaterials } from "./useMaterials";
import { useNotes } from "./useNotes";
import MaterialUpload from "./MaterialUpload";
import type { Material } from "../../shared/types";

interface SourcesPanelProps {
  courseId: string;
  collapsed: boolean;
  selectedSourceIds: string[];
  selectedNoteIds: string[];
  onSelectionChange: (sourceIds: string[], noteIds: string[]) => void;
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

function MaterialStatus({ status }: { status: string }) {
  if (status === "processing") {
    return <Loader2 className="w-3.5 h-3.5 text-foxAmber animate-spin shrink-0" />;
  }
  if (status === "ready") {
    return <Check className="w-3.5 h-3.5 text-emerald-500 shrink-0" />;
  }
  if (status === "failed") {
    return <AlertTriangle className="w-3.5 h-3.5 text-red-500 shrink-0" />;
  }
  return null;
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

function ProgressSteps({ materialId, courseId }: { materialId: string; courseId: string }) {
  const steps = [
    { key: "parse", label: "解析" },
    { key: "skeleton", label: "结构图" },
    { key: "wiki", label: "Wiki" },
    { key: "chunk", label: "分块" },
    { key: "embed", label: "向量化" },
    { key: "completed", label: "就绪" },
  ];

  return (
    <div className="mt-2 pl-6 space-y-1.5">
      {steps.map((step, i) => (
        <div key={step.key} className="flex items-center gap-2">
          <div className={`w-1.5 h-1.5 rounded-full ${i < steps.length - 1 ? "bg-emerald-400" : "bg-slate-300"}`} />
          <span className={`text-xs ${i < steps.length - 1 ? "text-slate-600" : "text-slate-400"}`}>{step.label}</span>
        </div>
      ))}
    </div>
  );
}

export default function SourcesPanel({ courseId, collapsed, selectedSourceIds, selectedNoteIds, onSelectionChange }: SourcesPanelProps) {
  const { materials, refetch: refetchMaterials } = useMaterials(courseId);
  const { notes, deleteNote } = useNotes(courseId);
  const [showUpload, setShowUpload] = useState(false);
  const [expandedMaterial, setExpandedMaterial] = useState<string | null>(null);

  const allSourceIds = materials.map((m) => m.id);
  const allSelected = materials.length > 0 && selectedSourceIds.length === allSourceIds.length;

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
    refetchMaterials();
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
                      <MaterialStatus status={m.status} />
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
                  {isExpanded && m.status === "processing" && (
                    <ProgressSteps materialId={m.id} courseId={courseId} />
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
