import { useState } from "react";
import { Check, Copy, RefreshCw, ThumbsDown, ThumbsUp, AlertTriangle, ShieldOff, Sparkles, RotateCcw } from "lucide-react";
import type { ConfidenceStatus } from "../../shared/types";
import type { ChatMessage as ChatMessageType } from "./useChat";
import MarkdownRenderer from "./MarkdownRenderer";
import CitationCard from "./CitationCard";
import ToolCallIndicator from "./ToolCallIndicator";

const confidenceMeta: Record<ConfidenceStatus, { label: string; cls: string; emoji: string }> = {
  grounded:    { label: "有据可循", cls: "fox-conf-grounded",   emoji: "✓" },
  ambiguous:   { label: "可能不准", cls: "fox-conf-ambiguous",  emoji: "?" },
  out_of_scope:{ label: "超出范围", cls: "fox-conf-outofscope", emoji: "—" },
};

interface ChatMessageProps {
  message: ChatMessageType;
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

export default function ChatMessage({ message, onRegenerate, onFeedback }: ChatMessageProps) {
  const isUser = message.role === "user";
  const isRefusal = message.role === "assistant" && message.confidenceStatus === "out_of_scope";
  const isError = message.role === "assistant" && message.isError === true;
  const isStreaming = !!message.isStreaming;
  const conf = message.confidenceStatus ? confidenceMeta[message.confidenceStatus] : null;

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
      <FoxAvatar streaming={isStreaming} error={isError} />
      <div className="min-w-0 max-w-[82%]">
        {/* Bubble */}
        <div
          className={`rounded-2xl rounded-bl-sm px-4 py-3 text-sm shadow-soft border ${
            isError
              ? "bg-red-50 text-red-800 border-red-200"
              : isRefusal
                ? "bg-slate-50 text-slate-500 border-slate-200"
                : "bg-white text-midnightCharcoal border-slate-100"
          }`}
        >
          {/* Confidence + status line */}
          {(conf || isError) && (
            <div className="flex items-center gap-1.5 mb-2 text-[0.68rem]">
              {isError ? (
                <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-red-100 text-red-600 border border-red-200">
                  <AlertTriangle className="w-3 h-3" />
                  回答异常
                </span>
              ) : isRefusal ? (
                <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-slate-200/80 text-slate-500 border border-slate-300">
                  <ShieldOff className="w-3 h-3" />
                  拒绝回答
                </span>
              ) : conf ? (
                <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md ${message.confidenceStatus === "grounded" ? "bg-emerald-50 text-emerald-700 border border-emerald-200" : "bg-amber-50 text-amber-700 border border-amber-200"}`}>
                  <span className="font-mono">{conf.emoji}</span>
                  {conf.label}
                </span>
              ) : null}
            </div>
          )}

          {/* Body */}
          {isRefusal || isError ? (
            <div>
              <p className="whitespace-pre-wrap leading-relaxed">{message.content}</p>
              {isError && onRegenerate && (
                <button
                  onClick={onRegenerate}
                  className="mt-2 inline-flex items-center gap-1 text-xs text-foxAmber hover:text-amber-700 font-medium transition-colors"
                >
                  <RotateCcw className="w-3 h-3" />
                  重新提问
                </button>
              )}
            </div>
          ) : (
            <MarkdownRenderer content={message.content} streaming={isStreaming} variant="ai" />
          )}

          {/* Tool calls timeline */}
          {message.toolCalls && message.toolCalls.length > 0 && (
            <ToolCallIndicator toolCalls={message.toolCalls} light />
          )}

          {/* Citations */}
          {message.citations && message.citations.length > 0 && (
            <div className="mt-3 pt-3 border-t border-slate-100">
              <div className="flex items-center gap-1.5 text-[0.68rem] text-slate-500 mb-1.5">
                <Sparkles className="w-3 h-3 text-foxAmber" />
                参考了 {message.citations.length} 处材料
              </div>
              <div className="flex flex-wrap gap-1.5">
                {message.citations.map((c, i) => (
                  <CitationCard key={i} citation={c} index={i} light />
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Action toolbar (only for completed, non-error assistant messages) */}
        {!isError && !isRefusal && !isStreaming && (
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
