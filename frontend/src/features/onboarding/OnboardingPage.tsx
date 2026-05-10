import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Upload, FileText, CheckCircle } from "lucide-react";
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
    // Also persist to backend
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
    // Persist onboarding completion to backend
    api.put("/user/settings/onboarding").catch(() => {});
    navigate("/");
  };

  const handleTextSubmit = async () => {
    if (!textInput.trim() || !courseId) return;
    try {
      const formData = new FormData();
      const blob = new Blob([textInput], { type: "text/plain" });
      formData.append("file", blob, "老师讲了什么.txt");
      formData.append("kind", "text_note");
      await api.upload(`/courses/${courseId}/materials`, formData);
    } catch {
      // Non-blocking
    }
    setSubmitted(true);
  };

  return (
    <div className="min-h-[calc(100vh-4rem)] flex flex-col items-center justify-center p-6">
      {step === 0 && (
        <div className="text-center max-w-md">
          <div className="text-8xl mb-6">🦊</div>
          <h1 className="text-3xl font-bold text-midnightCharcoal mb-3">{foxCopy.onboarding.greeting}</h1>
          <p className="text-gray-500 mb-8">{foxCopy.onboarding.modePick}</p>
          <div className="flex gap-4 justify-center">
            <button
              onClick={() => handleModeChoice("exam")}
              className="px-8 py-4 rounded-2xl bg-red-500 text-white font-bold text-lg hover:bg-red-600 transition-colors shadow-lg"
            >
              {foxCopy.onboarding.examChoice}
            </button>
            <button
              onClick={() => handleModeChoice("study")}
              className="px-8 py-4 rounded-2xl bg-foxAmber text-midnightCharcoal font-bold text-lg hover:bg-foxAmber/90 transition-colors shadow-lg"
            >
              {foxCopy.onboarding.studyChoice}
            </button>
          </div>
        </div>
      )}

      {step === 1 && (
        <div className="text-center max-w-md">
          <div className="text-6xl mb-6">📚</div>
          <h2 className="text-2xl font-bold text-midnightCharcoal mb-3">{foxCopy.onboarding.createCourse}</h2>
          <p className="text-gray-400 text-sm mb-6">先建一门课，别空着手。</p>
          <div className="flex gap-4 justify-center mt-6">
            <button
              onClick={() => setImportOpen(true)}
              className="px-6 py-3 rounded-xl border-2 border-foxAmber text-foxAmber font-semibold hover:bg-foxAmber/10 transition-colors"
            >
              导入课程表
            </button>
            <button
              onClick={() => setCreateOpen(true)}
              className="px-6 py-3 rounded-xl bg-foxAmber text-midnightCharcoal font-semibold hover:bg-foxAmber/90 transition-colors"
            >
              手动创建
            </button>
          </div>
        </div>
      )}

      {step === 2 && (
        <div className="text-center max-w-lg w-full">
          <div className="text-6xl mb-6">📄</div>
          <h2 className="text-2xl font-bold text-midnightCharcoal mb-3">{foxCopy.onboarding.uploadPrompt}</h2>
          <div className="mt-8 p-6 border-2 border-dashed border-gray-300 rounded-2xl">
            {submitted ? (
              <div className="py-8">
                <CheckCircle className="w-12 h-12 mx-auto mb-3 text-green-500" />
                <p className="text-lg font-medium text-midnightCharcoal">已提交！</p>
                <button
                  onClick={handleUploadComplete}
                  className="mt-4 px-6 py-2.5 rounded-xl bg-foxAmber text-midnightCharcoal font-semibold hover:bg-foxAmber/90 transition-colors"
                >
                  {foxCopy.onboarding.done}
                </button>
              </div>
            ) : (
              <>
                <FileText className="w-10 h-10 mx-auto mb-3 text-gray-400" />
                <p className="text-sm text-gray-500 mb-4">{foxCopy.onboarding.noFile}</p>
                <textarea
                  value={textInput}
                  onChange={(e) => setTextInput(e.target.value)}
                  placeholder="比如：老师今天讲了第三章的前两节，重点是牛顿-莱布尼茨公式..."
                  className="w-full h-32 p-4 rounded-xl border border-gray-200 text-sm resize-none focus:outline-none focus:border-foxAmber transition-colors"
                />
                <button
                  onClick={handleTextSubmit}
                  disabled={!textInput.trim()}
                  className="mt-3 px-6 py-2.5 rounded-xl bg-foxAmber text-midnightCharcoal font-semibold hover:bg-foxAmber/90 transition-colors disabled:opacity-50"
                >
                  <Upload className="w-4 h-4 inline mr-2" />
                  提交
                </button>
              </>
            )}
          </div>
          {!submitted && (
            <button
              onClick={handleUploadComplete}
              className="mt-6 text-gray-400 text-sm hover:text-gray-600 transition-colors"
            >
              跳过，稍后再说
            </button>
          )}
        </div>
      )}

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
