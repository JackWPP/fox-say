import { useState } from "react";
import { Network, GitBranch, BookOpen, HelpCircle, Zap, FileText, Plus, X } from "lucide-react";
import { Button } from "../../components/ui/Button";
import { useNotes } from "./useNotes";
import NoteEditor from "./NoteEditor";

type ActiveView = "chat" | "skeleton" | "kg" | "lecture" | "quiz" | "review" | "materials";

const studioTools: { key: ActiveView; label: string; icon: typeof FileText; description: string }[] = [
  { key: "kg", label: "知识图谱", icon: Network, description: "概念关联图" },
  { key: "skeleton", label: "课程骨架", icon: GitBranch, description: "章节与核心概念" },
  { key: "lecture", label: "讲义视图", icon: BookOpen, description: "系统学习材料" },
  { key: "quiz", label: "练习模式", icon: HelpCircle, description: "测验与巩固" },
  { key: "review", label: "复习计划", icon: Zap, description: "复习计划与陪伴" },
  { key: "materials", label: "材料管理", icon: FileText, description: "上传与处理材料" },
];

interface StudioPanelProps {
  courseId: string;
  activeView: ActiveView;
  onViewChange: (view: ActiveView) => void;
  selectedNoteIds: string[];
  onNoteSelectionChange: (noteIds: string[]) => void;
}

export default function StudioPanel({ courseId, activeView, onViewChange, selectedNoteIds, onNoteSelectionChange }: StudioPanelProps) {
  const { notes, createNote, deleteNote } = useNotes(courseId);
  const [showNoteEditor, setShowNoteEditor] = useState(false);

  const toggleNote = (id: string) => {
    if (selectedNoteIds.includes(id)) {
      onNoteSelectionChange(selectedNoteIds.filter((n) => n !== id));
    } else {
      onNoteSelectionChange([...selectedNoteIds, id]);
    }
  };

  const handleCreateNote = async (title: string, content: string) => {
    const note = await createNote(title, content);
    onNoteSelectionChange([...selectedNoteIds, note.id]);
    setShowNoteEditor(false);
  };

  const handleDeleteNote = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    try {
      await deleteNote(id);
      onNoteSelectionChange(selectedNoteIds.filter((n) => n !== id));
    } catch { /* ignore */ }
  };

  return (
    <div className="flex flex-col h-full">
      <div className="h-12 px-4 flex items-center border-b border-slate-200 shrink-0">
        <span className="text-sm font-semibold text-slate-700">Studio</span>
      </div>
      <div className="flex-1 overflow-y-auto p-3">
        <div className="grid grid-cols-2 gap-2 mb-4">
          {studioTools.map((tool) => {
            const Icon = tool.icon;
            const isActive = activeView === tool.key;
            return (
              <button
                key={tool.key}
                onClick={() => onViewChange(tool.key)}
                className={`flex flex-col items-start gap-1.5 p-3 rounded-xl text-left transition-all ${
                  isActive
                    ? "bg-foxAmber/10 border-2 border-foxAmber/40"
                    : "bg-slate-50 border border-transparent hover:bg-white hover:border-slate-200 hover:shadow-md hover:-translate-y-0.5"
                }`}
              >
                <div className={`p-1.5 rounded-lg ${
                  isActive
                    ? "bg-foxAmber/20 text-foxAmber"
                    : "bg-white text-slate-500"
                }`}>
                  <Icon className="w-4 h-4" />
                </div>
                <p className={`text-xs font-semibold ${
                  isActive ? "text-foxAmber" : "text-midnightCharcoal"
                }`}>
                  {tool.label}
                </p>
                <p className={`text-[0.65rem] leading-tight ${
                  isActive ? "text-foxAmber/70" : "text-slate-500"
                }`}>
                  {tool.description}
                </p>
              </button>
            );
          })}
        </div>

        <div className="border-t border-slate-200 pt-4">
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm font-semibold text-slate-700">我的笔记</span>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setShowNoteEditor(true)}
              className="h-7 px-2 text-foxAmber hover:text-foxAmber hover:bg-amber-50"
            >
              <Plus className="w-3.5 h-3.5" />
              新建
            </Button>
          </div>

          {showNoteEditor && (
            <div className="mb-3">
              <NoteEditor
                courseId={courseId}
                onSave={handleCreateNote}
                onCancel={() => setShowNoteEditor(false)}
              />
            </div>
          )}

          <div className="space-y-2">
            {notes.map((n) => {
              const isSelected = selectedNoteIds.includes(n.id);
              return (
                <div
                  key={n.id}
                  onClick={() => toggleNote(n.id)}
                  className={`p-3 rounded-xl border cursor-pointer transition-all group ${
                    isSelected
                      ? "bg-foxAmber/10 border-foxAmber/30"
                      : "bg-white border-slate-200 hover:border-slate-300 hover:shadow-sm"
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex-1 min-w-0">
                      <p className={`text-sm font-medium truncate ${
                        isSelected ? "text-foxAmber" : "text-midnightCharcoal"
                      }`}>
                        {n.title}
                      </p>
                      <p className="text-xs text-slate-500 mt-0.5 line-clamp-2">
                        {n.content.slice(0, 30)}{n.content.length > 30 ? "..." : ""}
                      </p>
                      {n.updated_at && (
                        <p className="text-[0.65rem] text-slate-400 mt-1">
                          {n.updated_at.slice(0, 16).replace("T", " ")}
                        </p>
                      )}
                    </div>
                    <button
                      onClick={(e) => handleDeleteNote(e, n.id)}
                      className="p-1 rounded opacity-0 group-hover:opacity-100 hover:bg-red-50 text-slate-400 hover:text-red-500 transition-all shrink-0"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              );
            })}
            {notes.length === 0 && !showNoteEditor && (
              <p className="text-xs text-slate-400 text-center py-6">
                还没有笔记，点击"新建"创建第一条笔记吧
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
