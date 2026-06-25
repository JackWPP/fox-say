import { useNavigate } from "react-router-dom";
import { BookOpen, Clock, User, Zap, AlertCircle, Loader2, CheckCircle2, FileText } from "lucide-react";
import type { Course, CourseStatus } from "../../shared/types";
import { foxCopy } from "../../shared/fox-copy";
import { Badge } from "../../components/ui/Badge";

const statusBorderColors: Record<CourseStatus, string> = {
  empty: "border-l-slate-300",
  processing: "border-l-foxAmber fox-breathe",
  ready: "border-l-green-500",
  failed: "border-l-red-500",
};

const statusIconMap: Record<CourseStatus, React.ReactNode> = {
  empty: <FileText className="w-4 h-4 text-slate-400" />,
  processing: <Loader2 className="w-4 h-4 text-foxAmber animate-spin" />,
  ready: <CheckCircle2 className="w-4 h-4 text-green-500" />,
  failed: <AlertCircle className="w-4 h-4 text-red-500" />,
};

const statusBadgeVariants: Record<CourseStatus, "default" | "amber" | "success" | "error"> = {
  empty: "default",
  processing: "amber",
  ready: "success",
  failed: "error",
};

const statusLabels: Record<CourseStatus, string> = {
  empty: "空课程",
  processing: "处理中",
  ready: "就绪",
  failed: "出错",
};

function formatCountdown(examDate?: string): { text: string; urgent: boolean } | null {
  if (!examDate) return null;
  const exam = new Date(examDate);
  const now = new Date();
  const diffMs = exam.getTime() - now.getTime();
  if (diffMs < 0) return { text: "已过期", urgent: true };
  const diffDays = Math.ceil(diffMs / (1000 * 60 * 60 * 24));
  if (diffDays > 7) return { text: `距考试 ${diffDays} 天`, urgent: false };
  const diffHours = Math.ceil(diffMs / (1000 * 60 * 60));
  return { text: diffDays <= 3 ? `${diffHours}小时后考试` : `${diffDays}天后考试`, urgent: diffDays <= 7 };
}

export default function CourseCard({ course, materialCount = 0 }: { course: Course; materialCount?: number }) {
  const navigate = useNavigate();
  const countdown = formatCountdown(course.exam_date);

  return (
    <button
      onClick={() => navigate(`/courses/${course.id}`)}
      className={`w-full bg-white rounded-2xl shadow-soft hover:shadow-md hover:-translate-y-1 transition-all duration-200 ease-out p-5 text-left border border-slate-100 hover:border-foxAmber/40 group cursor-pointer border-l-4 ${statusBorderColors[course.status]}`}
    >
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-start gap-3 flex-1 min-w-0">
          <div className="p-2.5 rounded-xl bg-foxAmber/10 group-hover:bg-foxAmber/20 transition-colors shrink-0">
            <BookOpen className="w-5 h-5 text-foxAmber" />
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="font-bold text-lg leading-tight text-midnightCharcoal truncate">
              {course.title}
            </h3>
            {course.teacher && (
              <div className="flex items-center gap-1.5 text-sm text-slate-500 mt-1">
                <User className="w-3.5 h-3.5 shrink-0" />
                <span className="truncate">{course.teacher}</span>
              </div>
            )}
          </div>
        </div>
        <div className="shrink-0 ml-2 mt-1">
          {statusIconMap[course.status]}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2 mt-3">
        <Badge variant={statusBadgeVariants[course.status]} size="sm">
          {statusLabels[course.status]}
        </Badge>
        {countdown !== null && (
          <Badge variant={countdown.urgent ? "error" : "amber"} size="sm">
            <Clock className="w-3 h-3 mr-1" />
            {countdown.text}
          </Badge>
        )}
      </div>

      <div className="mt-3 pt-3 border-t border-slate-100 flex items-center justify-between">
        <span className="text-xs text-slate-400 flex items-center gap-1">
          <FileText className="w-3 h-3" />
          {materialCount} 份材料
        </span>
        {countdown?.urgent && localStorage.getItem("foxsay_mode") !== "exam" && (
          <span className="inline-flex items-center gap-1 text-xs text-red-500 font-medium">
            <Zap className="w-3 h-3" />
            {foxCopy.review.switchSuggestion}
          </span>
        )}
      </div>
    </button>
  );
}
