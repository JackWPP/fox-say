import { useState, type FormEvent } from "react";
import { X } from "lucide-react";
import { useCreateCourse } from "./useCourses";

interface CreateCourseModalProps {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}

export default function CreateCourseModal({ open, onClose, onCreated }: CreateCourseModalProps) {
  const [title, setTitle] = useState("");
  const [teacher, setTeacher] = useState("");
  const [examDate, setExamDate] = useState("");
  const { createCourse, loading, error } = useCreateCourse();

  if (!open) return null;

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await createCourse({
        title,
        teacher: teacher || undefined,
        exam_date: examDate || undefined,
      });
      setTitle("");
      setTeacher("");
      setExamDate("");
      onCreated();
      onClose();
    } catch {}
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div
        className="bg-white rounded-2xl shadow-xl w-full max-w-md mx-4 p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-lg font-bold text-midnightCharcoal">创建课程</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              课程标题 <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              required
              placeholder="例如：高等数学 A"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-foxAmber focus:border-foxAmber outline-none transition-all text-midnightCharcoal"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">教师名</label>
            <input
              type="text"
              value={teacher}
              onChange={(e) => setTeacher(e.target.value)}
              placeholder="例如：张教授"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-foxAmber focus:border-foxAmber outline-none transition-all text-midnightCharcoal"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">考试日期</label>
            <input
              type="date"
              value={examDate}
              onChange={(e) => setExamDate(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-foxAmber focus:border-foxAmber outline-none transition-all text-midnightCharcoal"
            />
          </div>

          {error && (
            <p className="text-sm text-red-500">{error}</p>
          )}

          <button
            type="submit"
            disabled={loading || !title.trim()}
            className="w-full py-2.5 bg-foxAmber hover:bg-foxAmber/90 disabled:bg-gray-300 text-midnightCharcoal font-semibold rounded-lg transition-colors"
          >
            {loading ? "创建中..." : "创建课程"}
          </button>
        </form>
      </div>
    </div>
  );
}
