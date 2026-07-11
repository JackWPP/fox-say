import { useEffect, useRef, useState } from "react";
import { FileText, Check, Copy, Loader2, X } from "lucide-react";
import { api, getCurrentSourceFragmentPreview } from "../../shared/api";
import type {
  AnswerCitation,
  Citation,
  SourceFragmentPreview,
  SourcePreview,
} from "../../shared/types";

type CitationLike = Citation | AnswerCitation;

interface CitationCardProps {
  citation: CitationLike;
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

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.(pdf|pptx?|txt|md)$/i;

function displayFileName(name: string): string {
  if (UUID_PATTERN.test(name)) {
    const ext = name.slice(name.lastIndexOf(".")).toLowerCase();
    if (ext === ".pdf") return "PDF 文档";
    if (ext === ".ppt" || ext === ".pptx") return "PPT 课件";
    return "文档";
  }
  return name;
}

/**
 * A V2 citation is deliberately recognized only by an explicit opaque
 * fragment ID.  File names and display locators are not identity keys and
 * must never be used to upgrade a legacy citation into a V2 one.
 */
function isV2Citation(citation: CitationLike): citation is AnswerCitation {
  const evidence = (citation as { evidence?: unknown }).evidence;
  if (!evidence || typeof evidence !== "object") return false;

  const fragmentId = (evidence as { fragment_id?: unknown }).fragment_id;
  return typeof fragmentId === "string" && fragmentId.trim().length > 0;
}

function hasEvidenceField(citation: CitationLike): boolean {
  return Object.prototype.hasOwnProperty.call(citation, "evidence");
}

function isLegacyCitation(citation: CitationLike): citation is Citation {
  return !hasEvidenceField(citation);
}

function v2DisplayLocator(citation: AnswerCitation): string {
  const locator = citation.evidence.locator;
  return typeof locator === "string" && locator.trim()
    ? locator
    : "当前材料片段";
}

function previewMatchesCitation(
  preview: SourceFragmentPreview,
  courseId: string,
  citation: AnswerCitation,
): boolean {
  const { evidence } = citation;
  return preview.course_id === courseId
    && preview.material_id === evidence.material_id
    && preview.material_revision === evidence.material_revision
    && preview.fragment_id === evidence.fragment_id;
}

function isNotFoundError(error: unknown): boolean {
  return error instanceof Error && /\b404\b/.test(error.message);
}

export default function CitationCard({ citation, index, courseId, materialId, light }: CitationCardProps) {
  const [copied, setCopied] = useState(false);
  const [showPreview, setShowPreview] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [legacyPreview, setLegacyPreview] = useState<SourcePreview | null>(null);
  const [fragmentPreview, setFragmentPreview] = useState<SourceFragmentPreview | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [v2ErrorRetryable, setV2ErrorRetryable] = useState(false);
  const previewGeneration = useRef(0);

  const v2Citation = isV2Citation(citation);
  const legacyCitation = isLegacyCitation(citation);
  const hasEvidence = !legacyCitation;
  const citationFileName = citation.file_name;
  const citationIdentity = v2Citation
    ? `v2:${citation.evidence.course_id}:${citation.evidence.material_id}:${citation.evidence.material_revision}:${citation.evidence.fragment_id}`
    : legacyCitation
      ? `legacy:${citation.file_name}:${citation.locator}`
      : `invalid-evidence:${citationFileName}`;
  const currentFragmentPreview = v2Citation
    && fragmentPreview
    && fragmentPreview.course_id === courseId
    && fragmentPreview.material_id === citation.evidence.material_id
    && fragmentPreview.material_revision === citation.evidence.material_revision
    && fragmentPreview.fragment_id === citation.evidence.fragment_id
    ? fragmentPreview
    : null;
  const currentLegacyPreview = legacyCitation ? legacyPreview : null;
  const citationLocator = v2Citation
    ? v2DisplayLocator(citation)
    : legacyCitation
      ? citation.locator
      : "未验证的材料引用";
  const canonicalFileName = currentFragmentPreview
    ? currentFragmentPreview.file_name
    : citation.file_name;
  const canonicalLocator = currentFragmentPreview
    ? currentFragmentPreview.locator
    : citationLocator;
  const displayName = displayFileName(canonicalFileName);
  const ref = `来自 ${displayName} · ${canonicalLocator}`;

  useEffect(() => {
    // Citation cards are frequently keyed by position in legacy lists.  Clear
    // all preview state when their evidence identity/scope changes so an old
    // fragment can never be shown for a new citation.
    previewGeneration.current += 1;
    setShowPreview(false);
    setPreviewLoading(false);
    setLegacyPreview(null);
    setFragmentPreview(null);
    setPreviewError(null);
    setV2ErrorRetryable(false);
  }, [citationIdentity, courseId, materialId]);

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
    if (showPreview) {
      setShowPreview(false);
      return;
    }

    if (!isLegacyCitation(citation)) {
      // V2 preview is only valid for the current course/material revision.
      // Do not fall back to the legacy DMAP/locator endpoint on any failure.
      setShowPreview(true);
      if (!isV2Citation(citation)) {
        setPreviewError("无法打开材料引用：缺少有效的 fragment ID。");
        return;
      }
      if (!courseId) {
        setPreviewError("无法打开当前材料引用：缺少课程上下文。");
        return;
      }
      if (citation.evidence.course_id && citation.evidence.course_id !== courseId) {
        setPreviewError("引用不属于当前课程，无法打开原文。");
        return;
      }
      if (currentFragmentPreview || (previewError && !v2ErrorRetryable)) return;

      setPreviewLoading(true);
      setPreviewError(null);
      setV2ErrorRetryable(false);
      const requestGeneration = previewGeneration.current;
      try {
        const preview = await getCurrentSourceFragmentPreview(
          courseId,
          citation.evidence.fragment_id,
        );
        if (previewGeneration.current !== requestGeneration) return;
        if (!previewMatchesCitation(preview, courseId, citation)) {
          setV2ErrorRetryable(false);
          setPreviewError("引用返回的证据与当前材料不匹配，无法显示原文。");
          return;
        }
        setFragmentPreview(preview);
      } catch (error) {
        if (previewGeneration.current !== requestGeneration) return;
        const missingCurrentFragment = isNotFoundError(error);
        setV2ErrorRetryable(!missingCurrentFragment);
        setPreviewError(
          missingCurrentFragment
            ? "引用不再属于当前材料版本，无法打开原文。"
            : "加载当前材料引用失败，请稍后重试。",
        );
      } finally {
        if (previewGeneration.current === requestGeneration) {
          setPreviewLoading(false);
        }
      }
      return;
    }

    if (!courseId) {
      handleCopy(e);
      return;
    }

    setShowPreview(true);
    if (currentLegacyPreview || previewError) return;
    setPreviewLoading(true);
    setPreviewError(null);
    const requestGeneration = previewGeneration.current;
    try {
      const dmapId = citation.locator.includes("dmap:") ? citation.locator.split("dmap:")[1]?.split(" ")[0] : undefined;
      if (!materialId) {
        setPreviewError("无法获取原文预览");
        return;
      }
      const data = await api.get<SourcePreview>(
        `/courses/${courseId}/materials/${materialId}/source-preview${dmapId ? `?dmap_id=${dmapId}` : ""}`
      );
      if (previewGeneration.current !== requestGeneration) return;
      setLegacyPreview(data);
    } catch {
      if (previewGeneration.current !== requestGeneration) return;
      setPreviewError("加载预览失败");
    } finally {
      if (previewGeneration.current === requestGeneration) {
        setPreviewLoading(false);
      }
    }
  };

  const pillClass = light ? "fox-citation-light" : "fox-citation";

  return (
    <div className="relative inline-block">
      <button
        type="button"
        onClick={handleClick}
        className={pillClass}
        title={`${ref} (点击${hasEvidence ? (courseId ? "查看当前材料原文" : "查看引用状态") : (courseId ? "查看原文" : "复制")})`}
      >
        <FileText className="w-3 h-3 shrink-0" />
        <span className="font-mono">[{index + 1}]</span>
        <span className="truncate max-w-[10rem]">{truncateFileName(displayName)}</span>
        <span className="opacity-60">· {canonicalLocator}</span>
        {copied ? (
          <Check className="w-3 h-3 shrink-0 text-emerald-400 fox-check" onClick={handleCopy} />
        ) : (
          <Copy className="w-3 h-3 shrink-0 opacity-50 hover:opacity-100" onClick={handleCopy} />
        )}
      </button>

      {showPreview && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setShowPreview(false)} />
          <div className="absolute bottom-full left-0 z-50 mb-2 w-80 bg-white rounded-xl shadow-lg border border-slate-200 p-4 fox-fade-in">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-medium text-slate-700 truncate flex-1">
                {displayName} · {canonicalLocator}
              </span>
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
            ) : currentFragmentPreview ? (
              <div className="text-sm text-slate-700 max-h-60 overflow-y-auto fox-scroll leading-relaxed whitespace-pre-wrap">
                {currentFragmentPreview.text}
              </div>
            ) : currentLegacyPreview ? (
              <div className="text-sm text-slate-700 max-h-60 overflow-y-auto fox-scroll leading-relaxed whitespace-pre-wrap">
                {currentLegacyPreview.text}
              </div>
            ) : null}
          </div>
        </>
      )}
    </div>
  );
}
