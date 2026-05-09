import { FileText, Loader2, CheckCircle, XCircle, Image, FileType } from "lucide-react";
import type { Material, MaterialKind, CourseStatus } from "../../shared/types";

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

export default function MaterialList({ materials }: { materials: Material[] }) {
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
      {materials.map((m) => {
        const Icon = kindIcons[m.kind] || FileText;
        return (
          <div
            key={m.id}
            className="flex items-center gap-3 bg-white rounded-lg border border-gray-100 px-4 py-3 hover:border-foxAmber/30 transition-colors"
          >
            <Icon className="w-5 h-5 text-foxAmber shrink-0" />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-midnightCharcoal truncate">
                {m.filename}
              </p>
              <p className="text-xs text-gray-400">{kindLabels[m.kind]}</p>
            </div>
            <div className="flex items-center gap-1.5 text-xs text-gray-500 shrink-0">
              <StatusIcon status={m.status} />
              <span>{statusText[m.status]}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
