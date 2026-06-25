import { useState } from "react";
import { FileText, Check, Copy, Loader2, X } from "lucide-react";
import { api } from "../../shared/api";
import type { Citation, SourcePreview } from "../../shared/types";

interface CitationCardProps {
  citation: Citation;
  index: number;
  courseId?: string;
  materialId?: string;
  light?: boolean;
}

function truncateFileName(name: string, max = 22): string {
  if (name.length <= max) return name;
  const ext = name.includes(".") ? name.slice(name.lastIndexOf(".")) : "";
  const stem = name.slice(0, name.length - ext.length);
  return stem.slice(0, max - ext.length - 1) + "…" + ext;
}

export default function CitationCard({ citation, index, courseId, materialId, light }: CitationCardProps) {
  const [copied, setCopied] = useState(false);
  const [showPreview, setShowPreview] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [preview, setPreview] = useState<SourcePreview | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);

  const ref = `来自 ${citation.file_name} · ${citation.locator}`;

  const handleCopy = async (e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText(ref);
    } catch {
      const ta = document.createElement("textarea");
      ta.value = ref;
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand("copy"); } catch { /* ignore */ }
      document.body.removeChild(ta);
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 1400);
  };

  const handleClick = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!courseId) {
      handleCopy(e);
      return;
    }
    if (showPreview) {
      setShowPreview(false);
      return;
    }
    setShowPreview(true);
    if (preview || previewError) return;
    setPreviewLoading(true);
    setPreviewError(null);
    try {
      const dmapId = citation.locator.includes("dmap:") ? citation.locator.split("dmap:")[1]?.split(" ")[0] : undefined;
      if (!materialId) {
        setPreviewError("无法获取原文预览");
        return;
      }
      const data = await api.get<SourcePreview>(
        `/courses/${courseId}/materials/${materialId}/source-preview${dmapId ? `?dmap_id=${dmapId}` : ""}`
      );
      setPreview(data);
    } catch {
      setPreviewError("加载预览失败");
    } finally {
      setPreviewLoading(false);
    }
  };

  const pillClass = light ? "fox-citation-light" : "fox-citation";

  return (
    <div className="relative inline-block">
      <button
        type="button"
        onClick={handleClick}
        className={pillClass}
        title={`${ref} (点击${courseId ? "查看原文" : "复制"})`}
      >
        <FileText className="w-3 h-3 shrink-0" />
        <span className="font-mono">[{index + 1}]</span>
        <span className="truncate max-w-[10rem]">{truncateFileName(citation.file_name)}</span>
        <span className="opacity-60">· {citation.locator}</span>
        {copied ? (
          <Check className="w-3 h-3 shrink-0 text-emerald-400 fox-check" onClick={handleCopy} />
        ) : (
          <Copy className="w-3 h-3 shrink-0 opacity-50 hover:opacity-100" onClick={handleCopy} />
        )}
      </button>

      {showPreview && courseId && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setShowPreview(false)} />
          <div className="absolute bottom-full left-0 z-50 mb-2 w-80 bg-white rounded-xl shadow-lg border border-slate-200 p-4 fox-fade-in">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-medium text-slate-700 truncate flex-1">{citation.file_name} · {citation.locator}</span>
              <button onClick={() => setShowPreview(false)} className="p-1 rounded hover:bg-slate-100 text-slate-400">
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
            {previewLoading ? (
              <div className="flex items-center justify-center py-8 text-slate-400">
                <Loader2 className="w-5 h-5 animate-spin mr-2" />
                <span className="text-sm">加载原文中…</span>
              </div>
            ) : previewError ? (
              <p className="text-sm text-red-500 py-4 text-center">{previewError}</p>
            ) : preview ? (
              <div className="text-sm text-slate-700 max-h-60 overflow-y-auto fox-scroll leading-relaxed whitespace-pre-wrap">
                {preview.text}
              </div>
            ) : null}
          </div>
        </>
      )}
    </div>
  );
}
