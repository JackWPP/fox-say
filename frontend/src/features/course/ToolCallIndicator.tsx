import { useState } from "react";
import {
  Search, Edit3, CheckCheck, Loader2, Check, ChevronDown, Activity, Workflow,
} from "lucide-react";
import type { AgentPhase } from "../../shared/types";
import type { ToolCallState } from "../../shared/types";

/**
 * V2 phase mapping.  Phases are friendly Chinese labels emitted by the
 * server (`display_message`) and surfaced here as a small timeline so the
 * user sees Fox working but never sees chain-of-thought text.
 */
const phaseLabels: Record<string, { label: string; icon: typeof Search }> = {
  retrieving: { label: "检索证据", icon: Search },
  composing: { label: "组织回答", icon: Edit3 },
  verifying: { label: "验证引用", icon: CheckCheck },
  warning: { label: "提示", icon: Activity },
};

function iconForPhase(phase: string): typeof Search {
  return phaseLabels[phase]?.icon ?? Workflow;
}

function labelForPhase(phase: string, display?: string): string {
  const fallback = phaseLabels[phase]?.label ?? phase;
  // Prefer the server-provided friendly Chinese label; fall back to a static
  // mapping when the server omits a display message.
  if (display && display.trim()) return display;
  return fallback;
}

interface ToolCallIndicatorProps {
  /** V2 phase timeline (preferred over legacy tool calls). */
  phases?: AgentPhase[];
  /** Legacy tool calls — still rendered for backwards compatibility. */
  toolCalls?: ToolCallState[];
  defaultCollapsed?: boolean;
  light?: boolean;
  /** Render in streaming-mode (no collapse button, last phase emphasised). */
  streaming?: boolean;
}

function summarizeArgs(args: Record<string, unknown> | undefined): string {
  if (!args) return "";
  const entries = Object.entries(args);
  if (entries.length === 0) return "";
  const parts = entries
    .filter(([, v]) => v !== null && v !== undefined && v !== "")
    .map(([k, v]) => `${k}=${typeof v === "string" ? v : JSON.stringify(v)}`);
  return parts.join(" · ");
}

/**
 * Renders either a V2 agent phase timeline (preferred) or the legacy tool
 * call list.  Streaming mode disables the collapse button so the user can
 * always see progress.
 */
export default function ToolCallIndicator({
  phases,
  toolCalls,
  defaultCollapsed = true,
  light = false,
  streaming = false,
}: ToolCallIndicatorProps) {
  const [collapsed, setCollapsed] = useState(defaultCollapsed);

  const textMuted = light ? "text-slate-400" : "text-warmWhite/45";
  const textMain = light ? "text-slate-600" : "text-warmWhite/90";
  const textLabel = light ? "text-slate-500 hover:text-foxAmber" : "text-warmWhite/70 hover:text-warmWhite";
  const borderColor = light ? "border-slate-200" : "border-warmWhite/10";
  const iconColor = light ? "text-slate-400" : "text-warmWhite/70";
  const doneColor = light ? "text-emerald-500" : "text-emerald-400";
  const doneDot = light ? "bg-emerald-500" : "bg-emerald-400/80";
  const activeDot = light ? "bg-foxAmber fox-breathe" : "bg-foxAmber fox-breathe";

  // V2 phase timeline branch — server-assembled labels, no args.
  if (phases && phases.length > 0) {
    const lastIndex = phases.length - 1;
    return (
      <div className="my-2 fox-fade-in">
        {!streaming && (
          <button
            type="button"
            onClick={() => setCollapsed(!collapsed)}
            className={`inline-flex items-center gap-1.5 text-xs ${textLabel} transition-colors group`}
          >
            <Activity className="w-3 h-3 text-foxAmber" />
            <span className="font-medium">思考路径 · {phases.length} 步</span>
            <ChevronDown className={`w-3 h-3 transition-transform ${collapsed ? "" : "rotate-180"}`} />
          </button>
        )}
        {!collapsed && (
          <ol className={`mt-2 space-y-1.5 pl-1 border-l ${borderColor} ml-1.5`}>
            {phases.map((p, i) => {
              const Icon = iconForPhase(p.phase);
              const isLast = i === lastIndex && streaming;
              return (
                <li
                  key={`${p.phase}-${i}`}
                  className="relative pl-4 fox-fade-in"
                  style={{ animationDelay: `${i * 30}ms` }}
                >
                  <span
                    className={`absolute left-[-5px] top-1.5 w-2 h-2 rounded-full ${
                      isLast ? activeDot : doneDot
                    }`}
                  />
                  <div className="flex items-center gap-1.5 text-xs">
                    {isLast
                      ? <Loader2 className="w-3 h-3 animate-spin text-foxAmber" />
                      : <Check className={`w-3 h-3 ${doneColor}`} />}
                    <Icon className={`w-3 h-3 ${iconColor}`} />
                    <span className={`${textMain} font-medium`}>{labelForPhase(p.phase, p.display_message)}</span>
                  </div>
                </li>
              );
            })}
          </ol>
        )}
      </div>
    );
  }

  // Legacy tool call branch.
  if (!toolCalls || toolCalls.length === 0) return null;
  const runningCount = toolCalls.filter((tc) => tc.status === "running").length;
  const allDone = runningCount === 0;

  return (
    <div className="my-2 fox-fade-in">
      <button
        type="button"
        onClick={() => setCollapsed(!collapsed)}
        className={`inline-flex items-center gap-1.5 text-xs ${textLabel} transition-colors group`}
      >
        <Activity className="w-3 h-3 text-foxAmber" />
        <span className="font-medium">
          {allDone
            ? `查了 ${toolCalls.length} 个工具`
            : `正在调用 ${runningCount} 个工具…`}
        </span>
        <ChevronDown className={`w-3 h-3 transition-transform ${collapsed ? "" : "rotate-180"}`} />
      </button>

      {!collapsed && (
        <ol className={`mt-2 space-y-1.5 pl-1 border-l ${borderColor} ml-1.5`}>
          {toolCalls.map((tc, i) => {
            const Icon = phaseLabels[tc.tool]?.icon ?? Search;
            const argsSummary = summarizeArgs(tc.args);
            return (
              <li
                key={tc.id}
                className="relative pl-4 fox-fade-in"
                style={{ animationDelay: `${i * 30}ms` }}
              >
                <span
                  className={`absolute left-[-5px] top-1.5 w-2 h-2 rounded-full ${
                    tc.status === "running" ? activeDot : doneDot
                  }`}
                />
                <div className="flex items-center gap-1.5 text-xs">
                  {tc.status === "running" ? (
                    <Loader2 className="w-3 h-3 animate-spin text-foxAmber" />
                  ) : (
                    <Check className={`w-3 h-3 ${doneColor}`} />
                  )}
                  <Icon className={`w-3 h-3 ${iconColor}`} />
                  <span className={`${textMain} font-medium`}>{tc.tool}</span>
                  {argsSummary && (
                    <span className={`${textMuted} font-mono text-[0.7rem] truncate max-w-[16rem]`} title={argsSummary}>
                      {argsSummary}
                    </span>
                  )}
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}