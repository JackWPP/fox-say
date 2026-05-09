import { RefreshCw } from "lucide-react";
import MaterialUpload from "./MaterialUpload";
import MaterialList from "./MaterialList";
import { useMaterials } from "./useMaterials";

interface MaterialsTabProps {
  courseId: string;
}

export default function MaterialsTab({ courseId }: MaterialsTabProps) {
  const { materials, loading, error, refetch } = useMaterials(courseId);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="w-6 h-6 border-2 border-foxAmber border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-center py-12">
        <p className="text-red-500 text-sm mb-3">加载失败: {error}</p>
        <button
          onClick={refetch}
          className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-red-500 border border-red-200 rounded-lg hover:bg-red-50 transition-colors"
        >
          <RefreshCw className="w-4 h-4" />
          重试
        </button>
      </div>
    );
  }

  return (
    <div>
      <MaterialUpload courseId={courseId} onUploaded={refetch} />
      <MaterialList courseId={courseId} materials={materials} />
    </div>
  );
}
