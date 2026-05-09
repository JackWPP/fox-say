import { Zap, Calendar, RefreshCw } from "lucide-react";
import { useReviewPlan, useBtw } from "./useReview";
import ReviewPlanView from "./ReviewPlanView";
import BtwInput from "./BtwInput";
import type { Course } from "../../shared/types";

interface ReviewTabProps {
  courseId: string;
  course?: Course;
}

function getCountdownText(examDate: string): { text: string; urgent: boolean } | null {
  const now = new Date();
  const exam = new Date(examDate);
  const diffMs = exam.getTime() - now.getTime();
  if (diffMs < 0) return { text: "考试已过期", urgent: true };
  const diffDays = Math.ceil(diffMs / (1000 * 60 * 60 * 24));
  if (diffDays > 7) return { text: `距离考试还有 ${diffDays} 天`, urgent: false };
  const diffHours = Math.ceil(diffMs / (1000 * 60 * 60));
  return { text: `距离考试还有 ${diffHours} 小时`, urgent: diffDays <= 3 };
}

export default function ReviewTab({ courseId, course }: ReviewTabProps) {
  const { plan, loading, error, generatePlan } = useReviewPlan(courseId);
  const { btwAnswer, askBtw, loading: btwLoading, clearBtw } = useBtw(courseId);

  const countdown = course?.exam_date ? getCountdownText(course.exam_date) : null;

  return (
    <div className="flex flex-col h-[calc(100vh-14rem)]">
      <div className="flex-1 overflow-y-auto px-1 py-2">
        {countdown && (
          <div className={`mb-4 flex items-center gap-2 border rounded-xl px-4 py-3 ${
            countdown.urgent
              ? "bg-red-500/10 border-red-500/20"
              : "bg-foxAmber/10 border-foxAmber/20"
          }`}>
            <Calendar className={`w-4 h-4 shrink-0 ${countdown.urgent ? "text-red-500" : "text-foxAmber"}`} />
            <span className={`text-sm font-medium ${countdown.urgent ? "text-red-500" : "text-midnightCharcoal"}`}>{countdown.text}</span>
          </div>
        )}

        {!plan && !loading && (
          <div className="flex flex-col items-center justify-center py-16 text-gray-400">
            <Zap className="w-12 h-12 mb-3 opacity-40" />
            <p className="text-lg mb-4">让小狐狸帮你备考 🦊</p>
            <button
              onClick={() => generatePlan(course?.exam_date)}
              disabled={loading}
              className="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-foxAmber text-midnightCharcoal font-semibold hover:bg-foxAmber/90 transition-colors disabled:opacity-50 shadow-sm"
            >
              让小狐狸帮你备考 🦊
            </button>
            {error && (
              <div className="mt-3 text-center">
                <p className="text-sm text-red-500 mb-2">{error}</p>
                <button
                  onClick={() => generatePlan(course?.exam_date)}
                  className="inline-flex items-center gap-2 px-3 py-1.5 text-xs font-medium text-red-500 border border-red-200 rounded-lg hover:bg-red-50 transition-colors"
                >
                  <RefreshCw className="w-3 h-3" />
                  重试
                </button>
              </div>
            )}
          </div>
        )}

        {loading && (
          <div className="flex flex-col items-center justify-center py-16">
            <div className="w-8 h-8 border-2 border-foxAmber border-t-transparent rounded-full animate-spin mb-3" />
            <p className="text-sm text-gray-400">小狐狸正在为你制定复习计划...</p>
          </div>
        )}

        {plan && !loading && (
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-bold text-midnightCharcoal">复习计划</h2>
              <button
                onClick={() => generatePlan(course?.exam_date)}
                className="text-xs px-3 py-1.5 rounded-full bg-foxAmber/10 text-foxAmber font-medium hover:bg-foxAmber/20 transition-colors"
              >
                重新生成
              </button>
            </div>
            <ReviewPlanView plan={plan} />
          </div>
        )}
      </div>

      <div className="pt-3 border-t border-gray-100">
        {btwLoading && !btwAnswer && (
          <div className="flex justify-start mb-3">
            <div className="bg-midnightCharcoal text-warmWhite rounded-2xl rounded-bl-sm px-4 py-3 text-sm">
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 bg-foxAmber rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                <div className="w-2 h-2 bg-foxAmber rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                <div className="w-2 h-2 bg-foxAmber rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
              </div>
            </div>
          </div>
        )}
        <BtwInput
          onSend={askBtw}
          loading={btwLoading}
          btwAnswer={btwAnswer}
          onBack={clearBtw}
        />
      </div>
    </div>
  );
}
