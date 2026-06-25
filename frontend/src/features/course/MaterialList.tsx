import { FileText, Loader2, CheckCircle, XCircle, Image, FileType, AlertTriangle, RotateCw } from "lucide-react";
import type { Material, MaterialKind, CourseStatus } from "../../shared/types";
import { useMaterialProgress, useRetryMaterial } from "./useMaterials";

const kindIcons: Record<MaterialKind, typeof FileText> = {
  pdf: FileText,
  ppt: FileType,
  image: Image,
  text_note: FileText,
};

const kindLabels: Record<MaterialKind, string> = {
  pdf: "PDF",
  ppt: "PPT",
  image: "图片",
  text_note: "文本",
};

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.(pdf|pptx?|txt|md)$/i;

const KIND_DISPLAY_LABELS: Record<string, string> = {
  pdf: "PDF 文档",
  ppt: "PPT 课件",
  text_note: "文本笔记",
  image: "图片",
};

function formatMaterialName(filename: string, kind: string, index: number): string {
  if (UUID_PATTERN.test(filename)) {
    const label = KIND_DISPLAY_LABELS[kind] || "材料";
    return `${label} ${index + 1}`;
  }
  return filename;
}

const stepLabels: Record<string, string> = {
  parsing: "正在解析",
  chunking: "正在分块",
  embedding: "正在嵌入",
  storing: "正在存储",
  skeleton_generating: "正在生成骨架",
  completed: "已完成",
  failed: "处理失败",
};

function StatusIcon({ status }: { status: CourseStatus }) {
  switch (status) {
    case "processing":
      return <Loader2 className="w-4 h-4 text-foxAmber animate-spin" />;
    case "ready":
      return <CheckCircle className="w-4 h-4 text-green-500" />;
    case "failed":
      return <XCircle className="w-4 h-4 text-red-500" />;
    default:
      return <div className="w-4 h-4 rounded-full bg-gray-300" />;
  }
}

const statusText: Record<CourseStatus, string> = {
  empty: "",
  processing: "处理中",
  ready: "就绪",
  failed: "失败",
};

function MaterialProgress({ courseId, material }: { courseId: string; material: Material }) {
  const progress = useMaterialProgress(
    material.status === "processing" ? courseId : "",
    material.status === "processing" ? material.id : null
  );

  if (material.status !== "processing" || !progress?.current_step) {
    return <span>{statusText[material.status]}</span>;
  }

  return <span className="text-foxAmber">{stepLabels[progress.current_step] || progress.current_step}</span>;
}

export default function MaterialList({ courseId, materials, onRetry }: { courseId: string; materials: Material[]; onRetry?: (materialId: string) => void }) {
  if (materials.length === 0) {
    return (
      <div className="text-center py-12 text-gray-400">
        <FileText className="w-12 h-12 mx-auto mb-3 opacity-40" />
        <p className="text-sm">还没有上传材料，拖拽文件到这里吧 🦊</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {materials.map((m, index) => {
        const Icon = kindIcons[m.kind] || FileText;
        return (
          <div
            key={m.id}
            className="flex items-center gap-3 bg-white rounded-lg border border-gray-100 px-4 py-3 hover:border-foxAmber/30 transition-colors"
          >
            <Icon className="w-5 h-5 text-foxAmber shrink-0" />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-midnightCharcoal truncate">
                {formatMaterialName(m.filename, m.kind, index)}
              </p>
              <div className="flex items-center gap-2">
                <p className="text-xs text-gray-400">{kindLabels[m.kind]}</p>
                {m.degraded && (
                  <span className="inline-flex items-center gap-1 text-xs text-amber-500">
                    <AlertTriangle className="w-3 h-3" />
                    降级处理
                  </span>
                )}
              </div>
            </div>
            <div className="flex items-center gap-1.5 text-xs text-gray-500 shrink-0">
              <StatusIcon status={m.status} />
              <MaterialProgress courseId={courseId} material={m} />
              {m.status === "failed" && onRetry && (
                <button
                  onClick={() => onRetry(m.id)}
                  className="ml-1 p-1 rounded hover:bg-red-50 text-red-400 hover:text-red-600 transition-colors"
                  title="重试"
                >
                  <RotateCw className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
