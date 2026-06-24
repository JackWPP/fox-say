import { useState } from "react";
import { Zap, Calendar, BookOpen, HelpCircle, CheckCircle, RefreshCw } from "lucide-react";
import { useReviewPlan, useBtw, useReviewSession, useReviewStep } from "./useReview";
import BtwInput from "./BtwInput";
import MarkdownRenderer from "./MarkdownRenderer";
import type { Course } from "../../shared/types";
import { foxCopy } from "../../shared/fox-copy";

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
  if (diffDays > 7) return { text: foxCopy.review.countdown.replace("{days}", String(diffDays)), urgent: false };
  const diffHours = Math.ceil(diffMs / (1000 * 60 * 60));
  if (diffDays <= 3) return { text: foxCopy.review.countdownUrgent.replace("{days}", String(diffHours)), urgent: true };
  return { text: foxCopy.review.countdownUrgent.replace("{days}", String(diffDays)), urgent: true };
}

const stepIcons = {
  teach: BookOpen,
  quiz: HelpCircle,
  review: CheckCircle,
};

const stepLabels = {
  teach: "讲解",
  quiz: "练习",
  review: "总结",
};

export default function ReviewTab({ courseId, course }: ReviewTabProps) {
  const { plan, loading: planLoading, error, generatePlan } = useReviewPlan(courseId);
  const { btwAnswer, askBtw, loading: btwLoading, clearBtw } = useBtw(courseId);
  const { progress, sessionLoading, startSession, advanceStep, completeSession } = useReviewSession(courseId);
  const { stepContent, loading: stepLoading, stepType, generateStep, setStepContent } = useReviewStep(courseId);
  const [sessionActive, setSessionActive] = useState(false);

  const countdown = course?.exam_date ? getCountdownText(course.exam_date) : null;
  const hasSession = progress.status === "active" || progress.status === "completed";
  const isComplete = progress.status === "completed";
  const totalDays = plan?.daily_plan?.length || 0;
  const currentDay = progress.current_day;

  const handleStartReview = async () => {
    let currentPlan = plan;
    if (!currentPlan) {
      currentPlan = await generatePlan(course?.exam_date);
    }
    if (!currentPlan) return;
    await startSession();
    setSessionActive(true);
    await generateStep(1, "teach");
  };

  const handleQuiz = () => generateStep(currentDay, "quiz");

  const handleReview = () => generateStep(currentDay, "review");

  const handleNextDay = async () => {
    const nextDay = currentDay + 1;
    if (plan && nextDay > plan.daily_plan.length) {
      await completeSession();
    } else {
      await advanceStep(nextDay, `day_${currentDay}`);
      setStepContent(null);
      await generateStep(nextDay, "teach");
    }
  };

  const active = sessionActive || hasSession;

  return (
    <div className="flex flex-col h-[calc(100vh-14rem)]">
      <div className="flex-1 overflow-y-auto px-1 py-2">
        {/* Countdown banner */}
        {countdown && (
          <div className={`mb-4 flex items-center gap-2 border rounded-xl px-4 py-3 ${
            countdown.urgent ? "bg-red-500/10 border-red-500/20" : "bg-foxAmber/10 border-foxAmber/20"
          }`}>
            <Calendar className={`w-4 h-4 shrink-0 ${countdown.urgent ? "text-red-500" : "text-foxAmber"}`} />
            <span className={`text-sm font-medium ${countdown.urgent ? "text-red-500" : "text-midnightCharcoal"}`}>{countdown.text}</span>
          </div>
        )}

        {/* Pre-session: Not started */}
        {!active && !planLoading && (
          <div className="flex flex-col items-center justify-center py-16 text-gray-400">
            <Zap className="w-12 h-12 mb-3 opacity-40" />
            <p className="text-lg mb-4">{plan ? foxCopy.review.prompt : foxCopy.review.noPlanPrompt}</p>
            <button
              onClick={handleStartReview}
              disabled={planLoading || sessionLoading}
              className="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-foxAmber text-midnightCharcoal font-semibold hover:bg-foxAmber/90 transition-colors disabled:opacity-50 shadow-sm"
            >
              {foxCopy.review.startSessionBtn}
            </button>
            {error && (
              <div className="mt-3 text-center">
                <p className="text-sm text-red-500 mb-2">{error}</p>
                <button
                  onClick={() => generatePlan(course?.exam_date)}
                  className="inline-flex items-center gap-2 px-3 py-1.5 text-xs font-medium text-red-500 border border-red-200 rounded-lg hover:bg-red-50 transition-colors"
                >
                  <RefreshCw className="w-3 h-3" />
                  {foxCopy.errors.retry}
                </button>
              </div>
            )}
          </div>
        )}

        {/* Loading plan */}
        {planLoading && (
          <div className="flex flex-col items-center justify-center py-16">
            <div className="w-8 h-8 border-2 border-foxAmber border-t-transparent rounded-full animate-spin mb-3" />
            <p className="text-sm text-gray-400">{foxCopy.review.generating}</p>
          </div>
        )}

        {/* Completed */}
        {isComplete && (
          <div className="text-center py-8">
            <div className="text-4xl mb-3">🎉</div>
            <p className="text-lg font-semibold text-midnightCharcoal">{foxCopy.review.allDone}</p>
          </div>
        )}

        {/* Active guided session */}
        {active && !isComplete && (
          <div className="space-y-4">
            {/* Day progress header */}
            {plan && (
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-lg font-bold text-midnightCharcoal">
                    Day {currentDay} / {totalDays}
                  </span>
                  {stepContent && !stepLoading && (
                    <span className="flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-foxAmber/10 text-foxAmber font-medium">
                      {(() => { const Icon = stepIcons[stepType]; return <Icon className="w-3 h-3" />; })()}
                      {stepLabels[stepType]}
                    </span>
                  )}
                </div>
                <div className="bg-gray-100 rounded-full h-1.5 w-24">
                  <div
                    className="bg-foxAmber h-1.5 rounded-full transition-all"
                    style={{ width: `${Math.min((currentDay / totalDays) * 100, 100)}%` }}
                  />
                </div>
              </div>
            )}

            {/* Step content area */}
            <div className="bg-white rounded-xl border border-gray-100 p-4 shadow-sm min-h-[200px]">
              {stepLoading && (
                <div className="flex items-center gap-3 py-8 justify-center">
                  <div className="w-5 h-5 border-2 border-foxAmber border-t-transparent rounded-full animate-spin" />
                  <span className="text-sm text-gray-400">{foxCopy.review.thinking}</span>
                </div>
              )}

              {!stepLoading && stepContent && (
                <MarkdownRenderer content={stepContent} />
              )}

              {!stepLoading && !stepContent && (
                <div className="flex flex-col items-center justify-center py-8 text-gray-400">
                  <BookOpen className="w-8 h-8 mb-2 opacity-40" />
                  <p className="text-sm">点击下方按钮开始</p>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Action buttons + /btw */}
      <div className="pt-3 border-t border-gray-100 space-y-3">
        {/* Step action buttons */}
        {active && !isComplete && (
          <div className="flex gap-3 justify-center">
            {stepType === "teach" && stepContent && !stepLoading && (
              <button
                onClick={handleQuiz}
                className="flex items-center gap-2 px-6 py-3 rounded-xl bg-foxAmber text-midnightCharcoal font-semibold hover:bg-foxAmber/90 transition-colors shadow-sm"
              >
                <HelpCircle className="w-4 h-4" />
                {foxCopy.review.nextQuizBtn}
              </button>
            )}
            {stepType === "quiz" && stepContent && !stepLoading && (
              <button
                onClick={handleReview}
                className="flex items-center gap-2 px-6 py-3 rounded-xl bg-foxAmber text-midnightCharcoal font-semibold hover:bg-foxAmber/90 transition-colors shadow-sm"
              >
                <CheckCircle className="w-4 h-4" />
                {foxCopy.review.showAnswerBtn}
              </button>
            )}
            {stepType === "review" && stepContent && !stepLoading && (
              <button
                onClick={handleNextDay}
                className="flex items-center gap-2 px-6 py-3 rounded-xl bg-green-500 text-white font-semibold hover:bg-green-600 transition-colors shadow-sm"
              >
                <CheckCircle className="w-4 h-4" />
                {currentDay >= totalDays ? "完成全部复习" : foxCopy.review.doneDayBtn}
              </button>
            )}
          </div>
        )}

        {/* /btw input */}
        {btwLoading && !btwAnswer && (
          <div className="flex justify-start">
            <div className="bg-midnightCharcoal text-warmWhite rounded-2xl rounded-bl-sm px-4 py-3 text-sm">
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 bg-foxAmber rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                <div className="w-2 h-2 bg-foxAmber rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                <div className="w-2 h-2 bg-foxAmber rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
              </div>
            </div>
          </div>
        )}
        <BtwInput onSend={askBtw} loading={btwLoading} btwAnswer={btwAnswer} onBack={clearBtw} />
      </div>
    </div>
  );
}
