import { useState, useRef, useEffect } from "react";
import { Send, Square } from "lucide-react";
import { foxCopy } from "../../shared/fox-copy";

interface ChatInputProps {
  onSend: (question: string) => void;
  loading: boolean;
  prefill?: string;
  onPrefillConsumed?: () => void;
  onStop?: () => void;
}

export default function ChatInput({ onSend, loading, prefill, onPrefillConsumed, onStop }: ChatInputProps) {
  const [value, setValue] = useState("");
  const taRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (prefill) {
      setValue(prefill);
      onPrefillConsumed?.();
      taRef.current?.focus();
    }
  }, [prefill, onPrefillConsumed]);

  const handleSend = () => {
    const trimmed = value.trim();
    if (!trimmed || loading) return;
    onSend(trimmed);
    setValue("");
    requestAnimationFrame(() => {
      if (taRef.current) taRef.current.style.height = "auto";
    });
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const canSend = !loading && value.trim().length > 0;
  const isBusy = loading;

  return (
    <div
      className={`flex items-end gap-2 bg-white border rounded-2xl px-4 py-3 shadow-sm transition-colors ${
        isBusy ? "border-foxAmber/30" : "border-gray-200 focus-within:border-foxAmber/60"
      }`}
    >
      <textarea
        ref={taRef}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={isBusy}
        placeholder={isBusy ? "狐狸还在想…" : foxCopy.chat.placeholder}
        rows={1}
        className="flex-1 resize-none text-sm text-midnightCharcoal placeholder-gray-400 focus:outline-none bg-transparent disabled:opacity-50"
        style={{ minHeight: "1.5rem", maxHeight: "6rem" }}
        onInput={(e) => {
          const el = e.currentTarget;
          el.style.height = "auto";
          el.style.height = `${Math.min(el.scrollHeight, 96)}px`;
        }}
      />
      {isBusy && onStop ? (
        <button
          onClick={onStop}
          className="p-2 rounded-xl bg-midnightCharcoal text-warmWhite hover:bg-black transition-colors shrink-0"
          title="停止生成"
          aria-label="停止生成"
        >
          <Square className="w-4 h-4" fill="currentColor" />
        </button>
      ) : (
        <button
          onClick={handleSend}
          disabled={!canSend}
          className="p-2 rounded-xl bg-foxAmber text-midnightCharcoal hover:bg-amber-500 disabled:opacity-30 disabled:cursor-not-allowed transition-all shrink-0 shadow-sm"
          aria-label="发送"
        >
          <Send className="w-4 h-4" />
        </button>
      )}
    </div>
  );
}
