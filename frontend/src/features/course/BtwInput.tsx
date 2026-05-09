import { useState } from "react";
import { Send, FileText, ShieldCheck, HelpCircle, ShieldX, ArrowLeft } from "lucide-react";
import type { BtwInterjection, ConfidenceStatus } from "../../shared/types";

const confidenceConfig: Record<ConfidenceStatus, { label: string; color: string; Icon: typeof ShieldCheck }> = {
  grounded: { label: "有据可依", color: "bg-green-100 text-green-700", Icon: ShieldCheck },
  ambiguous: { label: "不太确定", color: "bg-foxAmber/20 text-foxAmber", Icon: HelpCircle },
  out_of_scope: { label: "超出范围", color: "bg-red-100 text-red-600", Icon: ShieldX },
};

interface BtwInputProps {
  onSend: (question: string) => void;
  loading: boolean;
  btwAnswer: BtwInterjection | null;
  onBack: () => void;
}

export default function BtwInput({ onSend, loading, btwAnswer, onBack }: BtwInputProps) {
  const [value, setValue] = useState("");

  const handleSend = () => {
    const trimmed = value.trim();
    if (!trimmed || loading) return;
    onSend(trimmed);
    setValue("");
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="space-y-3">
      {btwAnswer && (
        <div className="bg-midnightCharcoal text-warmWhite rounded-2xl rounded-bl-sm px-4 py-3 text-sm">
          <p className="whitespace-pre-wrap">{btwAnswer.answer.answer}</p>

          {btwAnswer.answer.citations && btwAnswer.answer.citations.length > 0 && (
            <div className="mt-3 pt-3 border-t border-white/10 space-y-1.5">
              {btwAnswer.answer.citations.map((c, i) => (
                <div key={i} className="flex items-center gap-1.5 text-xs opacity-80">
                  <FileText className="w-3 h-3 shrink-0" />
                  <span>来自 {c.file_name} · {c.locator}</span>
                </div>
              ))}
            </div>
          )}

          {btwAnswer.answer.confidence_status && (() => {
            const status = btwAnswer.answer.confidence_status as ConfidenceStatus;
            const cfg = confidenceConfig[status];
            const ConfIcon = cfg.Icon;
            return (
              <div className="mt-2">
                <span className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full font-medium ${cfg.color}`}>
                  <ConfIcon className="w-3 h-3" />
                  {cfg.label}
                </span>
              </div>
            );
          })()}

          <button
            onClick={onBack}
            className="mt-3 inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full bg-foxAmber text-midnightCharcoal font-medium hover:bg-foxAmber/90 transition-colors"
          >
            <ArrowLeft className="w-3 h-3" />
            返回复习
          </button>
        </div>
      )}

      <div className="flex items-end gap-2 bg-white border border-gray-200 rounded-2xl px-4 py-3 shadow-sm">
        <span className="text-foxAmber font-mono text-sm font-bold shrink-0 pb-0.5">/btw</span>
        <textarea
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={loading}
          placeholder="插句话..."
          rows={1}
          className="flex-1 resize-none text-sm text-midnightCharcoal placeholder-gray-400 focus:outline-none bg-transparent disabled:opacity-50"
          style={{ minHeight: "1.5rem", maxHeight: "6rem" }}
          onInput={(e) => {
            const el = e.currentTarget;
            el.style.height = "auto";
            el.style.height = `${Math.min(el.scrollHeight, 96)}px`;
          }}
        />
        <button
          onClick={handleSend}
          disabled={loading || !value.trim()}
          className="p-2 rounded-xl bg-foxAmber text-midnightCharcoal hover:bg-foxAmber/90 disabled:opacity-40 disabled:cursor-not-allowed transition-colors shrink-0"
        >
          <Send className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
