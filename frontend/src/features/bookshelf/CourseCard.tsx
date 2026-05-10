import { useNavigate } from "react-router-dom";
import { BookOpen, Clock, User, Zap } from "lucide-react";
import type { Course, CourseStatus } from "../../shared/types";
import { foxCopy } from "../../shared/fox-copy";

const statusColors: Record<CourseStatus, string> = {
  empty: "bg-gray-300",
  processing: "bg-foxAmber",
  ready: "bg-green-500",
  failed: "bg-red-500",
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
  if (diffDays > 7) return { text: `${diffDays}天后`, urgent: false };
  const diffHours = Math.ceil(diffMs / (1000 * 60 * 60));
  return { text: `${diffHours}小时后`, urgent: diffDays <= 3 };
}

export default function CourseCard({ course }: { course: Course }) {
  const navigate = useNavigate();
  const countdown = formatCountdown(course.exam_date);

  return (
    <button
      onClick={() => navigate(`/courses/${course.id}`)}
      className="bg-white rounded-xl shadow-md hover:shadow-lg transition-all duration-200 p-5 text-left border border-gray-100 hover:border-foxAmber/40 group cursor-pointer"
    >
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2 text-midnightCharcoal">
          <BookOpen className="w-5 h-5 text-foxAmber group-hover:scale-110 transition-transform" />
          <h3 className="font-semibold text-lg leading-tight truncate max-w-[180px]">
            {course.title}
          </h3>
        </div>
        <span className={`w-2.5 h-2.5 rounded-full shrink-0 ${statusColors[course.status]}`} title={statusLabels[course.status]} />
      </div>

      {course.teacher && (
        <div className="flex items-center gap-1.5 text-sm text-gray-500 mb-2">
          <User className="w-3.5 h-3.5" />
          <span>{course.teacher}</span>
        </div>
      )}

      {countdown !== null && (
        <div className={`flex items-center gap-1.5 text-sm ${
          countdown.urgent ? "text-red-500 font-semibold" : "text-foxAmber"
        }`}>
          <Clock className="w-3.5 h-3.5" />
          <span>考试: {countdown.text}</span>
        </div>
      )}

      <div className="mt-3 pt-3 border-t border-gray-100 flex items-center justify-between">
        <span className="text-xs text-gray-400">{statusLabels[course.status]}</span>
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
