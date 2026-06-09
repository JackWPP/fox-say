import { useState } from "react";
import {
  Search, BookOpen, Map, FileQuestion, ListTree, ArrowLeft, FileCode, Zap,
  Loader2, Check, ChevronDown, Wrench,
} from "lucide-react";
import type { ToolCallState } from "../../shared/types";

const toolLabels: Record<string, { label: string; icon: typeof Search; description: string }> = {
  search_wiki:        { label: "搜索 Wiki",        icon: Search,        description: "在课程知识库中检索相关词条" },
  get_course_map:     { label: "获取课程索引",      icon: Map,           description: "拉取本课章节结构与核心概念" },
  get_concept:        { label: "获取知识点",        icon: FileQuestion,  description: "查询某个核心概念的详细解释" },
  get_chapter_outline:{ label: "获取章节摘要",      icon: ListTree,      description: "拉取章节大纲与关键结论" },
  follow_prerequisite:{ label: "追溯先修链",        icon: ArrowLeft,     description: "回溯依赖此概念的前置知识" },
  get_source_content: { label: "获取原始材料",      icon: FileCode,      description: "读取 PDF / PPT 中的原文片段" },
  get_review_plan:    { label: "获取复习计划",      icon: Zap,           description: "拉取本课复习计划" },
};

interface ToolCallIndicatorProps {
  toolCalls: ToolCallState[];
  /** 是否折叠(默认折叠,等有调用时再展开) */
  defaultCollapsed?: boolean;
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

export default function ToolCallIndicator({ toolCalls, defaultCollapsed = true }: ToolCallIndicatorProps) {
  const [collapsed, setCollapsed] = useState(defaultCollapsed);

  if (toolCalls.length === 0) return null;

  const runningCount = toolCalls.filter((tc) => tc.status === "running").length;
  const allDone = runningCount === 0;

  return (
    <div className="my-2 fox-fade-in">
      <button
        type="button"
        onClick={() => setCollapsed(!collapsed)}
        className="inline-flex items-center gap-1.5 text-xs text-warmWhite/70 hover:text-warmWhite transition-colors group"
      >
        <Wrench className="w-3 h-3 text-foxAmber" />
        <span className="font-medium">
          {allDone
            ? `查了 ${toolCalls.length} 个工具`
            : `正在调用 ${runningCount} 个工具…`}
        </span>
        <ChevronDown className={`w-3 h-3 transition-transform ${collapsed ? "" : "rotate-180"}`} />
      </button>

      {!collapsed && (
        <ol className="mt-2 space-y-1.5 pl-1 border-l border-warmWhite/10 ml-1.5">
          {toolCalls.map((tc, i) => {
            const info = toolLabels[tc.tool] || { label: tc.tool, icon: Search, description: "" };
            const Icon = info.icon;
            const argsSummary = summarizeArgs(tc.args);
            return (
              <li
                key={tc.id}
                className="relative pl-4 fox-fade-in"
                style={{ animationDelay: `${i * 30}ms` }}
              >
                <span
                  className={`absolute left-[-5px] top-1.5 w-2 h-2 rounded-full ${
                    tc.status === "running"
                      ? "bg-foxAmber fox-breathe"
                      : "bg-emerald-400/80"
                  }`}
                />
                <div className="flex items-center gap-1.5 text-xs">
                  {tc.status === "running" ? (
                    <Loader2 className="w-3 h-3 animate-spin text-foxAmber" />
                  ) : (
                    <Check className="w-3 h-3 text-emerald-400" />
                  )}
                  <Icon className="w-3 h-3 text-warmWhite/70" />
                  <span className="text-warmWhite/90 font-medium">{info.label}</span>
                  {argsSummary && (
                    <span className="text-warmWhite/45 font-mono text-[0.7rem] truncate max-w-[16rem]" title={argsSummary}>
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
