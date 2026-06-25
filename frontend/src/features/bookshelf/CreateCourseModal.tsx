import { useState, type FormEvent } from "react";
import { X } from "lucide-react";
import { useCreateCourse } from "./useCourses";
import { Button } from "../../components/ui/Button";
import { Input } from "../../components/ui/Input";
import { Card } from "../../components/ui/Card";

interface CreateCourseModalProps {
  open: boolean;
  onClose: () => void;
  onCreated: (courseId: string) => void;
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
      const course = await createCourse({
        title,
        teacher: teacher || undefined,
        exam_date: examDate || undefined,
      });
      setTitle("");
      setTeacher("");
      setExamDate("");
      if (course) onCreated(course.id);
      onClose();
    } catch {}
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm" onClick={onClose}>
      <Card
        padding="lg"
        shadow="lg"
        className="w-full max-w-md mx-4 rounded-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-xl font-bold text-midnightCharcoal">创建课程</h2>
          <Button variant="icon" onClick={onClose} className="h-8 w-8">
            <X className="w-5 h-5" />
          </Button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1.5">
              课程标题 <span className="text-red-500">*</span>
            </label>
            <Input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              required
              placeholder="例如：高等数学 A"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1.5">教师名</label>
            <Input
              type="text"
              value={teacher}
              onChange={(e) => setTeacher(e.target.value)}
              placeholder="例如：张教授"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1.5">考试日期</label>
            <Input
              type="date"
              value={examDate}
              onChange={(e) => setExamDate(e.target.value)}
            />
          </div>

          {error && (
            <p className="text-sm text-red-500 bg-red-50 rounded-lg p-3">{error}</p>
          )}

          <Button
            type="submit"
            disabled={loading || !title.trim()}
            loading={loading}
            className="w-full rounded-xl h-11 text-base"
            size="lg"
          >
            {loading ? "创建中..." : "创建课程"}
          </Button>
        </form>
      </Card>
    </div>
  );
}
