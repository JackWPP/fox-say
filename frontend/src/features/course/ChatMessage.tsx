import { useState } from "react";
import {
  Check,
  Copy,
  RefreshCw,
  ThumbsDown,
  ThumbsUp,
  AlertTriangle,
  ShieldOff,
  Sparkles,
  RotateCcw,
  BookMarked,
  ChevronDown,
} from "lucide-react";
import type {
  AgentPhase,
  AnswerCitation,
  AnswerEnvelope,
  ConfidenceStatus,
} from "../../shared/types";
import type { ChatMessage as ChatMessageType, TermHit } from "./useChat";
import { deriveAnswerState } from "./useChat";
import MarkdownRenderer from "./MarkdownRenderer";
import CitationCard from "./CitationCard";
import ToolCallIndicator from "./ToolCallIndicator";

interface ConfidenceMeta {
  label: string;
  cls: string;
  emoji: string;
}

const confidenceMeta: Record<Exclude<ConfidenceStatus, "out_of_scope">, ConfidenceMeta> = {
  grounded: { label: "基于本课材料", cls: "fox-conf-grounded", emoji: "✓" },
  ambiguous: { label: "材料有限 · 建议对照原文", cls: "fox-conf-ambiguous", emoji: "?" },
};

interface ChatMessageProps {
  message: ChatMessageType;
  courseId?: string;
  /** Phase timeline already collected by useChat (live streaming). */
  streamingPhases?: AgentPhase[];
  onRegenerate?: () => void;
  onFeedback?: (kind: "up" | "down") => void;
}

function ToolbarCopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const handle = async () => {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const ta = document.createElement("textarea");
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand("copy"); } catch { /* ignore */ }
      document.body.removeChild(ta);
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 1400);
  };
  return (
    <button
      type="button"
      onClick={handle}
      className="p-1.5 rounded-md text-gray-500 hover:text-foxAmber hover:bg-gray-100 transition-colors"
      title={copied ? "已复制" : "复制全文"}
      aria-label="复制消息"
    >
      {copied
        ? <Check className="w-3.5 h-3.5 text-emerald-600 fox-check" />
        : <Copy className="w-3.5 h-3.5" />}
    </button>
  );
}

function TermHitsPanel({ terms }: { terms: TermHit[] }) {
  const [open, setOpen] = useState(false);
  if (!terms.length) return null;
  return (
    <div className="mt-3 pt-3 border-t border-slate-100">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 text-[0.68rem] text-violet-600 hover:text-violet-700 transition-colors w-full text-left"
      >
        <BookMarked className="w-3 h-3 shrink-0" />
        <span className="font-medium">词典命中 {terms.length} 条</span>
        <ChevronDown className={`w-3 h-3 ml-auto transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div className="mt-2 space-y-1.5">
          {terms.map((t, i) => (
            <div key={i} className="rounded-lg bg-violet-50 border border-violet-100 px-3 py-2">
              <div className="flex items-center gap-2">
                <span className="text-[0.72rem] font-semibold text-violet-700">{t.name}</span>
                <span className="ml-auto text-[0.6rem] text-violet-400 font-mono">score {t.score.toFixed(2)}</span>
              </div>
              <p className="text-[0.7rem] text-slate-600 mt-0.5 leading-snug">{t.definition}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function FoxAvatar({ streaming, error }: { streaming?: boolean; error?: boolean }) {
  return (
    <div
      className={`shrink-0 w-8 h-8 rounded-full bg-gradient-to-br from-foxAmber to-amber-600 flex items-center justify-center text-base shadow-md select-none ${
        streaming ? "fox-breathe" : ""
      } ${error ? "ring-2 ring-red-400/50" : ""}`}
      aria-hidden="true"
    >
      🦊
    </div>
  );
}

/**
 * Maps the four V2 envelope states onto a single badge line so the bubble
 * keeps the existing visual hierarchy (one badge + content + actions).
 *
 * - grounded/ambiguous + material -> "基于本课材料" / "材料有限"
 * - out_of_scope + supplementary  -> "本课材料未覆盖 · Fox 补充"
 * - unavailable (error)           -> red "回答异常"
 */
function AnswerStateBadge({
  state,
  envelope,
}: {
  state: ReturnType<typeof deriveAnswerState>;
  envelope: AnswerEnvelope | null;
}) {
  if (state.isUnavailable) {
    return (
      <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-red-100 text-red-600 border border-red-200">
        <AlertTriangle className="w-3 h-3" />
        回答异常
      </span>
    );
  }
  if (state.isSupplementary) {
    // out_of_scope: confidence may be "out_of_scope" or null; either way
    // we render the explicit "本课材料未覆盖" label because that is what
    // the user actually needs to know.
    return (
      <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-slate-200/80 text-slate-600 border border-slate-300">
        <ShieldOff className="w-3 h-3" />
        本课材料未覆盖 · Fox 补充
      </span>
    );
  }
  // Material answer — grounded or ambiguous.
  const confidence = state.confidenceStatus as Exclude<ConfidenceStatus, "out_of_scope"> | null;
  if (confidence && confidenceMeta[confidence]) {
    const meta = confidenceMeta[confidence];
    return (
      <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md ${meta.cls}`}>
        <span className="font-mono">{meta.emoji}</span>
        {meta.label}
      </span>
    );
  }
  // Material answer with no confidence (defensive fallback)
  return (
    <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-foxAmber/15 text-amber-700 border border-amber-200">
      <Sparkles className="w-3 h-3" />
      基于本课材料
    </span>
  );
}

function CitationsBlock({
  citations,
  courseId,
}: {
  citations: AnswerCitation[];
  courseId?: string;
}) {
  if (!citations.length) return null;
  return (
    <div className="mt-3 pt-3 border-t border-slate-100">
      <div className="flex items-center gap-1.5 text-[0.68rem] text-slate-500 mb-1.5">
        <Sparkles className="w-3 h-3 text-foxAmber" />
        参考了 {citations.length} 处材料
      </div>
      <div className="flex flex-wrap gap-1.5">
        {citations.map((c, i) => (
          <CitationCard
            key={`${c.evidence.fragment_id}-${i}`}
            citation={c}
            index={i}
            courseId={courseId}
            light
          />
        ))}
      </div>
    </div>
  );
}

export default function ChatMessage({
  message,
  courseId,
  streamingPhases,
  onRegenerate,
  onFeedback,
}: ChatMessageProps) {
  const isUser = message.role === "user";
  const state = deriveAnswerState(message);
  const isUnavailable = state.isUnavailable || message.isError === true;
  const isStreaming = !!message.isStreaming && !isUnavailable;
  // "refusal-like" means: no material citations and we deliberately render
  // the answer as plain text (no markdown), to avoid dressing up Fox's
  // honest fallback in markdown weight.
  const isRefusalLike = state.isSupplementary && !state.isUnavailable;
  const envelope = message.envelope ?? null;

  const phasesForRender: AgentPhase[] | undefined = isStreaming
    ? streamingPhases ?? message.phases
    : message.phases;

  // ---- User bubble ----
  if (isUser) {
    return (
      <div className="flex justify-end fox-fade-in group">
        <div className="flex items-end gap-2 max-w-[70%]">
          <div className="opacity-0 group-hover:opacity-100 transition-opacity">
            <button
              type="button"
              onClick={async () => {
                try { await navigator.clipboard.writeText(message.content); } catch { /* ignore */ }
              }}
              className="p-1.5 rounded-md text-gray-400 hover:text-gray-600 hover:bg-slate-100 transition-colors"
              title="复制"
              aria-label="复制消息"
            >
              <Copy className="w-3.5 h-3.5" />
            </button>
          </div>
          <div className="bg-gradient-to-br from-foxAmber to-orange-400 text-white rounded-2xl rounded-br-sm px-4 py-2.5 text-sm shadow-[0_2px_12px_-2px_rgba(245,158,11,0.35)] whitespace-pre-wrap break-words leading-relaxed">
            {message.content}
          </div>
        </div>
      </div>
    );
  }

  // ---- Assistant bubble ----
  return (
    <div className="flex justify-start gap-2.5 fox-fade-in group">
      <FoxAvatar streaming={isStreaming} error={isUnavailable} />
      <div className="min-w-0 max-w-[82%]">
        {/* Bubble */}
        <div
          className={`rounded-2xl rounded-bl-sm px-4 py-3 text-sm shadow-soft border ${
            isUnavailable
              ? "bg-red-50 text-red-800 border-red-200"
              : isRefusalLike
                ? "bg-slate-50 text-slate-500 border-slate-200"
                : "bg-white text-midnightCharcoal border-slate-100"
          }`}
        >
          {/* Confidence + status line */}
          <div className="flex items-center gap-1.5 mb-2 text-[0.68rem] flex-wrap">
            <AnswerStateBadge state={state} envelope={envelope} />
          </div>

          {/* Body */}
          {isUnavailable ? (
            <div>
              <p className="whitespace-pre-wrap leading-relaxed">
                {envelope?.error?.error_detail
                  || envelope?.error?.error_code
                  || message.content
                  || "回答生成失败"}
              </p>
              {onRegenerate && (
                <button
                  onClick={onRegenerate}
                  className="mt-2 inline-flex items-center gap-1 text-xs text-foxAmber hover:text-amber-700 font-medium transition-colors"
                >
                  <RotateCcw className="w-3 h-3" />
                  重新提问
                </button>
              )}
            </div>
          ) : isRefusalLike ? (
            <p className="whitespace-pre-wrap leading-relaxed">{message.content}</p>
          ) : (
            <MarkdownRenderer content={message.content} streaming={isStreaming} variant="ai" />
          )}

          {/* Phase timeline: shown while streaming, hidden once finalised. */}
          {isStreaming && phasesForRender && phasesForRender.length > 0 && (
            <ToolCallIndicator phases={phasesForRender} light streaming />
          )}

          {/* Citations — only ever render material citations from the envelope. */}
          {state.isMaterial && message.citations && message.citations.length > 0 && (
            <CitationsBlock citations={message.citations} courseId={courseId} />
          )}

          {/* Legacy compat: term hits from Qdrant dictionary */}
          {message.termHits && <TermHitsPanel terms={message.termHits} />}
        </div>

        {/* Action toolbar (only for completed, non-error, non-supplementary messages) */}
        {!isUnavailable && !isRefusalLike && !isStreaming && (
          <div className="flex items-center gap-0.5 mt-1 ml-1 opacity-0 group-hover:opacity-100 transition-opacity">
            <ToolbarCopyButton text={message.content} />
            {onRegenerate && (
              <button
                type="button"
                onClick={onRegenerate}
                className="p-1.5 rounded-md text-slate-400 hover:text-foxAmber hover:bg-slate-100 transition-colors"
                title="重新生成"
                aria-label="重新生成"
              >
                <RefreshCw className="w-3.5 h-3.5" />
              </button>
            )}
            {onFeedback && (
              <>
                <button
                  type="button"
                  onClick={() => onFeedback("up")}
                  className="p-1.5 rounded-md text-slate-400 hover:text-emerald-600 hover:bg-slate-100 transition-colors"
                  title="有帮助"
                  aria-label="有帮助"
                >
                  <ThumbsUp className="w-3.5 h-3.5" />
                </button>
                <button
                  type="button"
                  onClick={() => onFeedback("down")}
                  className="p-1.5 rounded-md text-slate-400 hover:text-red-500 hover:bg-slate-100 transition-colors"
                  title="没帮助"
                  aria-label="没帮助"
                >
                  <ThumbsDown className="w-3.5 h-3.5" />
                </button>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}