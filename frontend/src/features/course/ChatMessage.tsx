import { FileText, ShieldCheck, HelpCircle, ShieldX } from "lucide-react";
import type { ChatMessage as ChatMessageType, ConfidenceStatus } from "./useChat";

const confidenceConfig: Record<ConfidenceStatus, { label: string; color: string; Icon: typeof ShieldCheck }> = {
  grounded: { label: "有据可依", color: "bg-green-100 text-green-700", Icon: ShieldCheck },
  ambiguous: { label: "不太确定", color: "bg-foxAmber/20 text-foxAmber", Icon: HelpCircle },
  out_of_scope: { label: "超出范围", color: "bg-red-100 text-red-600", Icon: ShieldX },
};

export default function ChatMessage({ message }: { message: ChatMessageType }) {
  const isUser = message.role === "user";
  const isRefusal = message.role === "assistant" && message.confidenceStatus === "out_of_scope";

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[75%] bg-foxAmber text-midnightCharcoal rounded-2xl rounded-br-sm px-4 py-3 text-sm">
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start">
      <div
        className={`max-w-[80%] rounded-2xl rounded-bl-sm px-4 py-3 text-sm ${
          isRefusal
            ? "bg-gray-100 text-gray-400"
            : "bg-midnightCharcoal text-warmWhite"
        }`}
      >
        {isRefusal && (
          <span className="inline-block mr-1.5">🦊</span>
        )}
        <p className="whitespace-pre-wrap">{message.content}</p>

        {message.citations && message.citations.length > 0 && (
          <div className="mt-3 pt-3 border-t border-white/10 space-y-1.5">
            {message.citations.map((c, i) => (
              <div
                key={i}
                className="flex items-center gap-1.5 text-xs opacity-80"
              >
                <FileText className="w-3 h-3 shrink-0" />
                <span>来自 {c.file_name} · {c.locator}</span>
              </div>
            ))}
          </div>
        )}

        {message.confidenceStatus && (() => {
          const status = message.confidenceStatus as ConfidenceStatus;
          const cfg = confidenceConfig[status];
          const ConfIcon = cfg.Icon;
          return (
            <div className="mt-2">
              <span
                className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full font-medium ${cfg.color}`}
              >
                <ConfIcon className="w-3 h-3" />
                {cfg.label}
              </span>
            </div>
          );
        })()}
      </div>
    </div>
  );
}
