import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Upload, FileText, CheckCircle, Zap, BookOpen, Table2, Plus } from "lucide-react";
import { foxCopy } from "../../shared/fox-copy";
import CreateCourseModal from "../bookshelf/CreateCourseModal";
import ImportTimetableModal from "../bookshelf/ImportTimetableModal";
import { api } from "../../shared/api";

type Step = 0 | 1 | 2;

function loadOnboardingState(): { step: Step; courseId: string | null } {
  try {
    const raw = localStorage.getItem("foxsay_onboarding_state");
    if (raw) return JSON.parse(raw);
  } catch { /* ignore */ }
  return { step: 0, courseId: null };
}

function saveOnboardingState(state: { step: Step; courseId: string | null }) {
  localStorage.setItem("foxsay_onboarding_state", JSON.stringify(state));
}

function StepDots({ current }: { current: Step }) {
  return (
    <div className="flex items-center gap-2 mb-10">
      {([0, 1, 2] as Step[]).map((i) => (
        <div
          key={i}
          className={`rounded-full transition-all duration-300 ${
            i === current
              ? "w-6 h-2.5 bg-foxAmber"
              : i < current
              ? "w-2.5 h-2.5 bg-foxAmber/40"
              : "w-2.5 h-2.5 bg-slate-200"
          }`}
        />
      ))}
    </div>
  );
}

function ChoiceCard({
  emoji,
  title,
  desc,
  color,
  onClick,
  delay = 0,
}: {
  emoji: string;
  title: string;
  desc: string;
  color: "red" | "amber";
  onClick: () => void;
  delay?: number;
}) {
  const base =
    color === "red"
      ? "border-red-200 hover:border-red-400 hover:bg-red-50 hover:shadow-[0_8px_24px_-4px_rgba(239,68,68,0.18)]"
      : "border-amber-200 hover:border-foxAmber hover:bg-amber-50 hover:shadow-[0_8px_24px_-4px_rgba(245,158,11,0.22)]";
  const iconBg = color === "red" ? "bg-red-100 text-red-500" : "bg-amber-100 text-foxAmber";

  return (
    <button
      onClick={onClick}
      style={{ animationDelay: `${delay}ms` }}
      className={`fox-stagger-in w-full text-left p-5 rounded-2xl border-2 bg-white transition-all duration-200 cursor-pointer group ${base}`}
    >
      <div className={`w-12 h-12 rounded-xl flex items-center justify-center text-2xl mb-3 ${iconBg} transition-transform duration-200 group-hover:scale-110`}>
        {emoji}
      </div>
      <div className="font-bold text-midnightCharcoal text-base mb-1">{title}</div>
      <div className="text-sm text-slate-500 leading-relaxed">{desc}</div>
    </button>
  );
}

export default function OnboardingPage() {
  const navigate = useNavigate();
  const saved = loadOnboardingState();
  const [step, setStep] = useState<Step>(saved.step);
  const [courseId, setCourseId] = useState<string | null>(saved.courseId);
  const [createOpen, setCreateOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [textInput, setTextInput] = useState("");
  const [submitted, setSubmitted] = useState(false);

  useEffect(() => {
    saveOnboardingState({ step, courseId });
  }, [step, courseId]);

  const handleModeChoice = (chosen: "exam" | "study") => {
    localStorage.setItem("foxsay_mode", chosen);
    api.put("/user/settings/mode", { mode: chosen }).catch(() => {});
    setStep(1);
  };

  const handleCourseCreated = (newCourseId: string) => {
    setCreateOpen(false);
    setCourseId(newCourseId);
    setStep(2);
  };

  const handleCourseImported = (newCourseIds: string[]) => {
    setImportOpen(false);
    if (newCourseIds.length > 0) {
      setCourseId(newCourseIds[0]);
      setStep(2);
    }
  };

  const handleUploadComplete = () => {
    localStorage.removeItem("foxsay_onboarding_state");
    localStorage.setItem("foxsay_onboarding_done", "true");
    api.put("/user/settings/onboarding").catch(() => {});
    window.location.href = "/";
  };

  const handleTextSubmit = async () => {
    if (!textInput.trim() || !courseId) return;
    try {
      const formData = new FormData();
      const blob = new Blob([textInput], { type: "text/plain" });
      formData.append("file", blob, "老师讲了什么.txt");
      formData.append("kind", "text_note");
      await api.upload(`/courses/${courseId}/materials`, formData);
    } catch { /* Non-blocking */ }
    setSubmitted(true);
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-6 bg-gradient-to-br from-amber-50 via-orange-50/60 to-rose-50/40 relative overflow-hidden">
      {/* Background blobs */}
      <div className="absolute top-[-80px] right-[-60px] w-72 h-72 bg-foxAmber/10 rounded-full blur-3xl pointer-events-none" />
      <div className="absolute bottom-[-60px] left-[-40px] w-56 h-56 bg-orange-300/10 rounded-full blur-3xl pointer-events-none" />

      <div className="relative w-full max-w-sm flex flex-col items-center">
        <StepDots current={step} />

        {/* ── Step 0: mode choice ── */}
        {step === 0 && (
          <div key="step0" className="fox-slide-up-in w-full text-center">
            <div className="text-7xl fox-float mb-5 select-none">🦊</div>
            <h1 className="text-3xl font-bold text-midnightCharcoal mb-2 tracking-tight">
              {foxCopy.onboarding.greeting}
            </h1>
            <p className="text-slate-500 mb-8 text-sm leading-relaxed">
              {foxCopy.onboarding.modePick}
            </p>
            <div className="grid grid-cols-2 gap-3">
              <ChoiceCard
                emoji="⚡"
                title={foxCopy.onboarding.examChoice}
                desc="考试快到了，帮你抓重点、刷题、制定复习计划。"
                color="red"
                onClick={() => handleModeChoice("exam")}
                delay={60}
              />
              <ChoiceCard
                emoji="📖"
                title={foxCopy.onboarding.studyChoice}
                desc="跟着课程节奏，每次课后消化、积累知识。"
                color="amber"
                onClick={() => handleModeChoice("study")}
                delay={120}
              />
            </div>
          </div>
        )}

        {/* ── Step 1: create course ── */}
        {step === 1 && (
          <div key="step1" className="fox-slide-up-in w-full text-center">
            <div className="text-6xl mb-5 select-none">📚</div>
            <h2 className="text-2xl font-bold text-midnightCharcoal mb-2 tracking-tight">
              {foxCopy.onboarding.createCourse}
            </h2>
            <p className="text-slate-500 text-sm mb-8">先建一门课，别空着手。</p>
            <div className="grid grid-cols-2 gap-3">
              <ChoiceCard
                emoji="📋"
                title="导入课程表"
                desc="上传 Excel/CSV，自动创建所有课程。"
                color="amber"
                onClick={() => setImportOpen(true)}
                delay={60}
              />
              <ChoiceCard
                emoji="✏️"
                title="手动创建"
                desc="填写课程名称，快速开始。"
                color="amber"
                onClick={() => setCreateOpen(true)}
                delay={120}
              />
            </div>
          </div>
        )}

        {/* ── Step 2: upload material ── */}
        {step === 2 && (
          <div key="step2" className="fox-slide-up-in w-full text-center">
            <div className="text-6xl mb-5 select-none">📄</div>
            <h2 className="text-2xl font-bold text-midnightCharcoal mb-2 tracking-tight">
              {foxCopy.onboarding.uploadPrompt}
            </h2>
            <p className="text-slate-500 text-sm mb-6">
              把课堂笔记、PPT 文字版丢给我，我来消化。
            </p>

            {submitted ? (
              <div
                className="fox-pop p-8 rounded-2xl bg-white border-2 border-green-200 shadow-soft"
              >
                <CheckCircle className="w-14 h-14 mx-auto mb-3 text-green-500" />
                <p className="text-lg font-bold text-midnightCharcoal mb-1">收到啦！🎉</p>
                <p className="text-sm text-slate-500 mb-5">正在后台帮你消化，稍等片刻。</p>
                <button
                  onClick={handleUploadComplete}
                  className="px-8 py-3 rounded-xl bg-foxAmber text-midnightCharcoal font-bold hover:bg-amber-400 transition-colors shadow-soft"
                >
                  {foxCopy.onboarding.done}
                </button>
              </div>
            ) : (
              <div className="rounded-2xl bg-white border-2 border-dashed border-amber-200 p-5 shadow-soft">
                <FileText className="w-9 h-9 mx-auto mb-2 text-amber-300" />
                <p className="text-xs text-slate-400 mb-3">{foxCopy.onboarding.noFile}</p>
                <textarea
                  value={textInput}
                  onChange={(e) => setTextInput(e.target.value)}
                  placeholder="比如：老师今天讲了第三章的前两节，重点是牛顿-莱布尼茨公式..."
                  className="w-full h-28 p-3.5 rounded-xl border border-slate-200 text-sm resize-none focus:outline-none focus:border-foxAmber transition-colors bg-slate-50/60"
                />
                <button
                  onClick={handleTextSubmit}
                  disabled={!textInput.trim()}
                  className="mt-3 w-full py-3 rounded-xl bg-foxAmber text-midnightCharcoal font-bold hover:bg-amber-400 transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                >
                  <Upload className="w-4 h-4" />
                  提交给小狐狸
                </button>
              </div>
            )}

            {!submitted && (
              <button
                onClick={handleUploadComplete}
                className="mt-5 text-slate-400 text-sm hover:text-slate-600 transition-colors underline underline-offset-2"
              >
                跳过，稍后再说
              </button>
            )}
          </div>
        )}
      </div>

      <CreateCourseModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={handleCourseCreated}
      />
      <ImportTimetableModal
        open={importOpen}
        onClose={() => setImportOpen(false)}
        onImported={handleCourseImported}
      />
    </div>
  );
}
