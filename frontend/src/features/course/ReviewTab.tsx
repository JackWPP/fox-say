import { useState } from "react";
import { Zap, Calendar, BookOpen, HelpCircle, CheckCircle, RefreshCw } from "lucide-react";
import { useReviewPlan, useBtw, useReviewSession, useReviewStep } from "./useReview";
import BtwInput from "./BtwInput";
import MarkdownRenderer from "./MarkdownRenderer";
import type { Course } from "../../shared/types";
import { foxCopy } from "../../shared/fox-copy";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { Badge } from "../../components/ui/Badge";
import { Spinner } from "../../components/ui/Spinner";

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

const stepBadgeVariants = {
  teach: "amber" as const,
  quiz: "info" as const,
  review: "success" as const,
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
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto px-4 py-4">
        {countdown && (
          <div className={`mb-5 flex items-center gap-3 border rounded-2xl px-5 py-4 ${
            countdown.urgent
              ? "bg-gradient-to-r from-red-50 to-orange-50 border-red-200"
              : "bg-gradient-to-r from-amber-50 to-orange-50 border-foxAmber/30"
          }`}>
            <div className={`p-2 rounded-xl ${countdown.urgent ? "bg-red-100" : "bg-foxAmber/20"}`}>
              <Calendar className={`w-5 h-5 shrink-0 ${countdown.urgent ? "text-red-500" : "text-foxAmber"}`} />
            </div>
            <span className={`text-sm font-semibold ${countdown.urgent ? "text-red-600" : "text-midnightCharcoal"}`}>
              {countdown.text}
            </span>
          </div>
        )}

        {!active && !planLoading && (
          <div className="flex flex-col items-center justify-center py-16">
            <div className="p-4 rounded-2xl bg-foxAmber/10 mb-4">
              <Zap className="w-12 h-12 text-foxAmber" />
            </div>
            <p className="text-lg font-medium text-midnightCharcoal mb-6">
              {plan ? foxCopy.review.prompt : foxCopy.review.noPlanPrompt}
            </p>
            <Button
              onClick={handleStartReview}
              disabled={planLoading || sessionLoading}
              loading={planLoading || sessionLoading}
              size="lg"
              className="rounded-2xl px-8 py-6 text-base"
            >
              {foxCopy.review.startSessionBtn}
            </Button>
            {error && (
              <div className="mt-4 text-center">
                <p className="text-sm text-red-500 mb-3">{error}</p>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => generatePlan(course?.exam_date)}
                >
                  <RefreshCw className="w-3.5 h-3.5" />
                  {foxCopy.errors.retry}
                </Button>
              </div>
            )}
          </div>
        )}

        {planLoading && (
          <div className="flex flex-col items-center justify-center py-16">
            <Spinner size="lg" className="mb-4" />
            <p className="text-sm text-slate-500">{foxCopy.review.generating}</p>
          </div>
        )}

        {isComplete && (
          <div className="text-center py-12">
            <div className="text-5xl mb-4">🎉</div>
            <p className="text-xl font-bold text-midnightCharcoal mb-2">{foxCopy.review.allDone}</p>
            <p className="text-sm text-slate-500">恭喜你完成了全部复习计划！</p>
          </div>
        )}

        {active && !isComplete && (
          <div className="space-y-5">
            {plan && (
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <span className="text-xl font-bold text-midnightCharcoal">
                    Day {currentDay} / {totalDays}
                  </span>
                  {stepContent && !stepLoading && (
                    <Badge variant={stepBadgeVariants[stepType]} size="md">
                      {(() => { const Icon = stepIcons[stepType]; return <Icon className="w-3.5 h-3.5 mr-1" />; })()}
                      {stepLabels[stepType]}
                    </Badge>
                  )}
                </div>
                <div className="bg-slate-100 rounded-full h-2 w-32 overflow-hidden">
                  <div
                    className="h-2 rounded-full bg-gradient-to-r from-foxAmber to-amber-400 transition-all duration-500"
                    style={{ width: `${Math.min((currentDay / totalDays) * 100, 100)}%` }}
                  />
                </div>
              </div>
            )}

            <Card padding="lg" shadow="soft" className="rounded-2xl min-h-[240px]">
              {stepLoading && (
                <div className="flex items-center gap-3 py-12 justify-center">
                  <Spinner size="md" />
                  <span className="text-sm text-slate-500">{foxCopy.review.thinking}</span>
                </div>
              )}

              {!stepLoading && stepContent && (
                <MarkdownRenderer content={stepContent} ai />
              )}

              {!stepLoading && !stepContent && (
                <div className="flex flex-col items-center justify-center py-12 text-slate-400">
                  <BookOpen className="w-10 h-10 mb-3 opacity-50" />
                  <p className="text-sm">点击下方按钮开始</p>
                </div>
              )}
            </Card>
          </div>
        )}
      </div>

      <div className="pt-4 border-t border-slate-100 space-y-4 px-4 pb-4 bg-white">
        {active && !isComplete && (
          <div className="flex gap-3 justify-center">
            {stepType === "teach" && stepContent && !stepLoading && (
              <Button
                onClick={handleQuiz}
                size="lg"
                className="rounded-2xl px-8"
              >
                <HelpCircle className="w-4 h-4" />
                {foxCopy.review.nextQuizBtn}
              </Button>
            )}
            {stepType === "quiz" && stepContent && !stepLoading && (
              <Button
                onClick={handleReview}
                size="lg"
                className="rounded-2xl px-8"
              >
                <CheckCircle className="w-4 h-4" />
                {foxCopy.review.showAnswerBtn}
              </Button>
            )}
            {stepType === "review" && stepContent && !stepLoading && (
              <Button
                onClick={handleNextDay}
                size="lg"
                className="rounded-2xl px-8 bg-green-500 hover:bg-green-600 text-white"
              >
                <CheckCircle className="w-4 h-4" />
                {currentDay >= totalDays ? "完成全部复习" : foxCopy.review.doneDayBtn}
              </Button>
            )}
          </div>
        )}

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
