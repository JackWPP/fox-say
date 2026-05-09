import { useState } from "react";
import { Send } from "lucide-react";

interface ChatInputProps {
  onSend: (question: string) => void;
  loading: boolean;
}

export default function ChatInput({ onSend, loading }: ChatInputProps) {
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
    <div className="flex items-end gap-2 bg-white border border-gray-200 rounded-2xl px-4 py-3 shadow-sm">
      <textarea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={loading}
        placeholder="问点关于课程的问题..."
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
  );
}
