import { useState } from "react";
import { FileText, Check, Copy } from "lucide-react";
import type { Citation } from "../../shared/types";

interface CitationCardProps {
  citation: Citation;
  index: number;
}

function truncateFileName(name: string, max = 22): string {
  if (name.length <= max) return name;
  const ext = name.includes(".") ? name.slice(name.lastIndexOf(".")) : "";
  const stem = name.slice(0, name.length - ext.length);
  return stem.slice(0, max - ext.length - 1) + "…" + ext;
}

export default function CitationCard({ citation, index }: CitationCardProps) {
  const [copied, setCopied] = useState(false);

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

  return (
    <button
      type="button"
      onClick={handleCopy}
      className="fox-citation"
      title={`${ref} (点击复制)`}
    >
      <FileText className="w-3 h-3 shrink-0" />
      <span className="font-mono">[{index + 1}]</span>
      <span className="truncate max-w-[10rem]">{truncateFileName(citation.file_name)}</span>
      <span className="opacity-60">· {citation.locator}</span>
      {copied ? (
        <Check className="w-3 h-3 shrink-0 text-emerald-400 fox-check" />
      ) : (
        <Copy className="w-3 h-3 shrink-0 opacity-50" />
      )}
    </button>
  );
}
