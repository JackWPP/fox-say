import { useState } from "react";
import { Plus, Table2, RefreshCw } from "lucide-react";
import CourseCard from "./CourseCard";
import CreateCourseModal from "./CreateCourseModal";
import ImportTimetableModal from "./ImportTimetableModal";
import { useCourses } from "./useCourses";

export default function BookshelfPage() {
  const { courses, loading, error, refetch } = useCourses();
  const [createOpen, setCreateOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);

  return (
    <div className="p-6 md:p-8 max-w-6xl mx-auto">
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-2xl font-bold text-midnightCharcoal">我的课程</h1>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setImportOpen(true)}
            className="flex items-center gap-2 px-4 py-2 border border-gray-300 rounded-lg text-sm font-medium text-midnightCharcoal hover:border-foxAmber hover:text-foxAmber transition-colors"
          >
            <Table2 className="w-4 h-4" />
            导入课程表
          </button>
          <button
            onClick={() => setCreateOpen(true)}
            className="flex items-center gap-2 px-4 py-2 bg-foxAmber rounded-lg text-sm font-semibold text-midnightCharcoal hover:bg-foxAmber/90 transition-colors"
          >
            <Plus className="w-4 h-4" />
            创建课程
          </button>
        </div>
      </div>

      {loading && (
        <div className="flex items-center justify-center py-20">
          <div className="w-8 h-8 border-2 border-foxAmber border-t-transparent rounded-full animate-spin" />
        </div>
      )}

      {error && (
        <div className="text-center py-20">
          <p className="text-red-500 mb-3">加载失败: {error}</p>
          <button
            onClick={refetch}
            className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-red-500 border border-red-200 rounded-lg hover:bg-red-50 transition-colors"
          >
            <RefreshCw className="w-4 h-4" />
            重试
          </button>
        </div>
      )}

      {!loading && !error && courses.length === 0 && (
        <div className="text-center py-20">
          <div className="text-6xl mb-4">🦊</div>
          <p className="text-lg text-gray-500 mb-2">还没有课程？让小狐狸帮你建立书架 🦊</p>
          <p className="text-sm text-gray-400">
            点击「创建课程」或「导入课程表」，开始你的学习之旅吧~
          </p>
        </div>
      )}

      {!loading && !error && courses.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-5">
          {courses.map((course) => (
            <CourseCard key={course.id} course={course} />
          ))}
        </div>
      )}

      <CreateCourseModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={refetch}
      />
      <ImportTimetableModal
        open={importOpen}
        onClose={() => setImportOpen(false)}
        onImported={refetch}
      />
    </div>
  );
}
