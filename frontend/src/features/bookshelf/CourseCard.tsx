import { useState, type FormEvent } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import { Clock, Zap, AlertCircle, Loader2, CheckCircle2, FileText, Pencil, X, Check } from "lucide-react";
import type { Course, CourseStatus } from "../../shared/types";
import { useUpdateCourse } from "./useCourses";
import EmojiPicker from "../../components/ui/EmojiPicker";

const statusConfig: Record<
  CourseStatus,
  { dot: string; label: string }
> = {
  empty:      { dot: "bg-slate-300",  label: "空课程" },
  processing: { dot: "bg-foxAmber",   label: "处理中" },
  ready:      { dot: "bg-green-400",  label: "就绪"   },
  failed:     { dot: "bg-red-400",    label: "出错"   },
};

const noteColors = [
  { bg: "bg-yellow-100", stripe: "bg-yellow-300/60", text: "text-yellow-900", input: "bg-yellow-50  border-yellow-200 focus:ring-yellow-300" },
  { bg: "bg-sky-100",    stripe: "bg-sky-300/60",    text: "text-sky-900",    input: "bg-sky-50     border-sky-200     focus:ring-sky-300"    },
  { bg: "bg-green-100",  stripe: "bg-green-300/60",  text: "text-green-900",  input: "bg-green-50   border-green-200   focus:ring-green-300"  },
  { bg: "bg-pink-100",   stripe: "bg-pink-300/60",   text: "text-pink-900",   input: "bg-pink-50    border-pink-200    focus:ring-pink-300"   },
  { bg: "bg-violet-100", stripe: "bg-violet-300/60", text: "text-violet-900", input: "bg-violet-50  border-violet-200  focus:ring-violet-300" },
  { bg: "bg-orange-100", stripe: "bg-orange-300/60", text: "text-orange-900", input: "bg-orange-50  border-orange-200  focus:ring-orange-300" },
];

const tilts = ["rotate-[-1.5deg]", "rotate-[0.5deg]", "rotate-[-0.8deg]", "rotate-[1.2deg]", "rotate-[0deg]", "rotate-[-1deg]"];

function getIdx(id: string, len: number) {
  return id.charCodeAt(0) % len;
}

function formatCountdown(examDate?: string): { text: string; urgent: boolean } | null {
  if (!examDate) return null;
  const exam = new Date(examDate);
  const now = new Date();
  const diffMs = exam.getTime() - now.getTime();
  if (diffMs < 0) return { text: "已过期", urgent: true };
  const diffDays = Math.ceil(diffMs / (1000 * 60 * 60 * 24));
  if (diffDays > 7) return { text: `距考试 ${diffDays} 天`, urgent: false };
  const diffHours = Math.ceil(diffMs / (1000 * 60 * 60));
  return { text: diffDays <= 3 ? `${diffHours}h 后考试` : `${diffDays}天后考试`, urgent: diffDays <= 7 };
}

interface CourseCardProps {
  course: Course;
  materialCount?: number;
  onUpdated?: () => void;
}

export default function CourseCard({ course, materialCount = 0, onUpdated }: CourseCardProps) {
  const navigate = useNavigate();
  const [editing, setEditing] = useState(false);
  const [editTitle, setEditTitle] = useState(course.title);
  const [editTeacher, setEditTeacher] = useState(course.teacher ?? "");
  const [editExamDate, setEditExamDate] = useState(course.exam_date ?? "");
  const [editIcon, setEditIcon] = useState(course.icon ?? "📚");
  const { updateCourse, loading: saving } = useUpdateCourse();

  const countdown = formatCountdown(course.exam_date);
  const cfg = statusConfig[course.status];
  const color = noteColors[getIdx(course.id, noteColors.length)];
  const tilt  = tilts[getIdx(course.id + "t", tilts.length)];

  function openEdit(e: React.MouseEvent) {
    e.stopPropagation();
    setEditTitle(course.title);
    setEditTeacher(course.teacher ?? "");
    setEditExamDate(course.exam_date ?? "");
    setEditIcon(course.icon ?? "📚");
    setEditing(true);
  }

  async function handleSave(e: FormEvent) {
    e.preventDefault();
    await updateCourse(course.id, {
      title: editTitle,
      teacher: editTeacher || undefined,
      exam_date: editExamDate || undefined,
      icon: editIcon,
    });
    setEditing(false);
    onUpdated?.();
  }

  return (
    <>
      {/* ── Sticky note card ── */}
      <button
        onClick={() => navigate(`/courses/${course.id}`)}
        className={`
          w-full aspect-square flex flex-col text-left
          ${color.bg} ${tilt}
          rounded-sm
          shadow-[3px_4px_10px_rgba(0,0,0,0.13),_1px_1px_0_rgba(255,255,255,0.6)_inset]
          hover:shadow-[5px_8px_20px_rgba(0,0,0,0.18),_1px_1px_0_rgba(255,255,255,0.6)_inset]
          hover:rotate-[0deg] hover:-translate-y-2 hover:scale-[1.03]
          transition-all duration-200 ease-out
          cursor-pointer group
          relative overflow-hidden
          p-4
        `}
      >
        {/* Top colour stripe */}
        <div className={`absolute top-0 left-0 right-0 h-7 ${color.stripe} flex items-center px-3 gap-1.5`}>
          <span className={`w-2 h-2 rounded-full ${cfg.dot}`} />
          <span className={`text-[0.65rem] font-semibold opacity-70 ${color.text}`}>{cfg.label}</span>
          {countdown?.urgent && (
            <span className="ml-auto text-[0.6rem] text-red-500 font-bold flex items-center gap-0.5">
              <Zap className="w-2.5 h-2.5" />{countdown.text}
            </span>
          )}
        </div>

        {/* Edit button – appears on hover */}
        <div
          role="button"
          aria-label="编辑课程"
          onClick={openEdit}
          className={`
            absolute top-[1.9rem] right-1.5 z-10
            w-6 h-6 rounded-full
            ${color.stripe} ${color.text}
            flex items-center justify-center
            opacity-0 group-hover:opacity-100
            hover:scale-110 active:scale-95
            transition-all duration-150
          `}
        >
          <Pencil className="w-3 h-3" />
        </div>

        {/* Body */}
        <div className="flex flex-col flex-1 mt-6">
          <span className="text-3xl mb-1 leading-none select-none">{course.icon ?? "📚"}</span>
          <h3 className={`font-bold text-sm leading-snug line-clamp-3 ${color.text} mb-auto`}>
            {course.title}
          </h3>
          {course.teacher && (
            <p className={`text-[0.7rem] opacity-60 mt-2 truncate ${color.text}`}>{course.teacher}</p>
          )}
          {countdown && !countdown.urgent && (
            <p className={`text-[0.65rem] opacity-55 mt-1 flex items-center gap-1 ${color.text}`}>
              <Clock className="w-2.5 h-2.5" />{countdown.text}
            </p>
          )}
        </div>

        {/* Footer */}
        <div className={`mt-3 pt-2 border-t border-black/8 flex items-center justify-between ${color.text}`}>
          <span className="text-[0.65rem] opacity-50 flex items-center gap-1">
            <FileText className="w-3 h-3" />
            {materialCount} 份材料
          </span>
          <span className="text-[0.65rem] opacity-40 group-hover:opacity-70 transition-opacity font-medium">→</span>
        </div>

        {/* Fold corner */}
        <div className="absolute bottom-0 right-0 w-5 h-5 overflow-hidden">
          <div className="absolute bottom-0 right-0 w-0 h-0 border-l-[20px] border-l-transparent border-b-[20px] border-b-black/10" />
        </div>
      </button>

      {/* ── Edit overlay — portalled to body to escape ancestor transforms ── */}
      {editing && createPortal(
        <>
          {/* Backdrop */}
          <div
            className="fixed inset-0 z-40 bg-black/50 backdrop-blur-[2px] fox-backdrop-in"
            onClick={() => setEditing(false)}
          />

          {/* Edit panel — sticky note style, lower portion of screen */}
          <div
            className={`
              fixed z-50 bottom-16 left-1/2
              w-80 rounded-sm overflow-hidden
              ${color.bg}
              shadow-[8px_14px_40px_rgba(0,0,0,0.28),_1px_1px_0_rgba(255,255,255,0.65)_inset]
              fox-note-pop
            `}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Top stripe */}
            <div className={`${color.stripe} h-8 flex items-center justify-between px-4`}>
              <div className="flex items-center gap-1.5">
                <span className="text-base select-none">{editIcon}</span>
                <span className={`text-[0.65rem] font-semibold opacity-70 ${color.text}`}>编辑课程</span>
              </div>
              <button
                type="button"
                onClick={() => setEditing(false)}
                className={`w-5 h-5 rounded-full flex items-center justify-center ${color.text} opacity-60 hover:opacity-100 hover:scale-110 transition-all`}
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>

            <form onSubmit={handleSave} className="p-4 space-y-3">
              {/* Icon picker */}
              <div>
                <p className={`text-xs font-semibold mb-2 opacity-60 ${color.text}`}>课程图标</p>
                <EmojiPicker value={editIcon} onChange={setEditIcon} />
              </div>

              {/* Title */}
              <div>
                <p className={`text-xs font-semibold mb-1 opacity-60 ${color.text}`}>课程标题</p>
                <input
                  type="text"
                  value={editTitle}
                  onChange={(e) => setEditTitle(e.target.value)}
                  required
                  autoFocus
                  className={`w-full rounded-lg px-3 py-2 text-sm border ${color.input} focus:outline-none focus:ring-2 ${color.text}`}
                />
              </div>

              {/* Teacher */}
              <div>
                <p className={`text-xs font-semibold mb-1 opacity-60 ${color.text}`}>教师名</p>
                <input
                  type="text"
                  value={editTeacher}
                  onChange={(e) => setEditTeacher(e.target.value)}
                  placeholder="可选"
                  className={`w-full rounded-lg px-3 py-2 text-sm border ${color.input} focus:outline-none focus:ring-2 ${color.text}`}
                />
              </div>

              {/* Exam date */}
              <div>
                <p className={`text-xs font-semibold mb-1 opacity-60 ${color.text}`}>考试日期</p>
                <input
                  type="date"
                  value={editExamDate}
                  onChange={(e) => setEditExamDate(e.target.value)}
                  className={`w-full rounded-lg px-3 py-2 text-sm border ${color.input} focus:outline-none focus:ring-2 ${color.text}`}
                />
              </div>

              {/* Actions */}
              <div className="flex gap-2 pt-1">
                <button
                  type="button"
                  onClick={() => setEditing(false)}
                  className={`flex-1 py-2 rounded-lg text-sm font-medium border ${color.input} ${color.text} opacity-70 hover:opacity-100 transition-opacity`}
                >
                  取消
                </button>
                <button
                  type="submit"
                  disabled={saving || !editTitle.trim()}
                  className={`flex-1 py-2 rounded-lg text-sm font-bold flex items-center justify-center gap-1.5 ${color.stripe} ${color.text} hover:brightness-95 disabled:opacity-50 transition-all`}
                >
                  {saving
                    ? <><Loader2 className="w-3.5 h-3.5 animate-spin" />保存中...</>
                    : <><Check className="w-3.5 h-3.5" />保存</>
                  }
                </button>
              </div>
            </form>

            {/* Fold corner */}
            <div className="absolute bottom-0 right-0 w-5 h-5 overflow-hidden">
              <div className="absolute bottom-0 right-0 w-0 h-0 border-l-[20px] border-l-transparent border-b-[20px] border-b-black/10" />
            </div>
          </div>
        </>,
        document.body
      )}
    </>
  );
}
