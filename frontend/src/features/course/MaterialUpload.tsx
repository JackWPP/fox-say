import { useRef, useState } from "react";
import { Upload, FileUp, AlertCircle, CheckCircle, X } from "lucide-react";
import { useUploadMaterials } from "./useMaterials";

const ACCEPTED = ".pdf,.ppt,.pptx,.png,.jpg,.jpeg,.txt,.md,.docx,.html";
const MAX_BATCH = 15;

interface FileStatus {
  name: string;
  size: number;
  status: "pending" | "uploading" | "done" | "failed";
  progress: number;
}

interface MaterialUploadProps {
  courseId: string;
  onUploaded: () => void;
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function MaterialUpload({ courseId, onUploaded }: MaterialUploadProps) {
  const [dragOver, setDragOver] = useState(false);
  const [fileStatuses, setFileStatuses] = useState<FileStatus[]>([]);
  const [batchError, setBatchError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const { upload, uploading, error } = useUploadMaterials(courseId);

  const handleFiles = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    setBatchError(null);

    if (files.length > MAX_BATCH) {
      setBatchError(`单次最多上传 ${MAX_BATCH} 个文件,你选择了 ${files.length} 个`);
      return;
    }

    const arr = Array.from(files);
    const initialStatuses: FileStatus[] = arr.map((f) => ({
      name: f.name,
      size: f.size,
      status: "pending",
      progress: 0,
    }));
    setFileStatuses(initialStatuses);

    try {
      // 标记所有文件为 uploading
      setFileStatuses((prev) => prev.map((s) => ({ ...s, status: "uploading", progress: 0 })));

      await upload(arr, (pct) => {
        // 真实上传进度(XMLHttpRequest onUploadProgress),分发到所有文件
        setFileStatuses((prev) =>
          prev.map((s) => (s.status === "uploading" ? { ...s, progress: pct } : s)),
        );
      });

      // 全部完成
      setFileStatuses((prev) => prev.map((s) => ({ ...s, status: "done", progress: 100 })));
      onUploaded();
      // 3 秒后清空列表
      setTimeout(() => setFileStatuses([]), 3000);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "上传失败";
      // 标记未完成的文件为 failed(HEC-1,前端可见错误)
      setFileStatuses((prev) =>
        prev.map((s) => (s.status === "uploading" ? { ...s, status: "failed" } : s)),
      );
      setBatchError(msg);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    handleFiles(e.dataTransfer.files);
  };

  const clearList = () => {
    setFileStatuses([]);
    setBatchError(null);
  };

  const hasActiveFiles = fileStatuses.length > 0;
  const doneCount = fileStatuses.filter((s) => s.status === "done").length;
  const overallProgress =
    hasActiveFiles && uploading
      ? Math.round(fileStatuses.reduce((sum, s) => sum + s.progress, 0) / fileStatuses.length)
      : 0;

  return (
    <div className="mb-6">
      <div
        onDrop={handleDrop}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onClick={() => !uploading && inputRef.current?.click()}
        className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all ${
          dragOver ? "border-foxAmber bg-foxAmber/5" : "border-gray-300 hover:border-foxAmber"
        } ${uploading ? "pointer-events-none opacity-60" : ""}`}
      >
        {uploading ? (
          <div className="space-y-3">
            <FileUp className="w-10 h-10 text-foxAmber mx-auto animate-bounce" />
            <p className="text-sm text-gray-600">
              上传中... {doneCount}/{fileStatuses.length} 完成 ({overallProgress}%)
            </p>
            <div className="w-full bg-gray-200 rounded-full h-2">
              <div
                className="bg-foxAmber h-2 rounded-full transition-all duration-300"
                style={{ width: `${overallProgress}%` }}
              />
            </div>
          </div>
        ) : hasActiveFiles && fileStatuses.every((s) => s.status === "done") ? (
          <div className="space-y-2">
            <CheckCircle className="w-10 h-10 text-green-500 mx-auto" />
            <p className="text-sm text-green-600">
              {fileStatuses.length} 个文件上传成功!
            </p>
          </div>
        ) : (
          <>
            <Upload className="w-10 h-10 text-gray-400 mx-auto mb-3" />
            <p className="text-sm text-gray-500 mb-1">
              拖拽文件到此处,或点击选择(支持多选)
            </p>
            <p className="text-xs text-gray-400">
              支持 PDF/PPT/Word/HTML/图片/文本,单次最多 {MAX_BATCH} 个文件
            </p>
          </>
        )}
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED}
          multiple
          onChange={(e) => handleFiles(e.target.files)}
          className="hidden"
        />
      </div>

      {/* 文件列表(每个文件独立状态) */}
      {hasActiveFiles && (
        <div className="mt-3 space-y-1.5 max-h-60 overflow-y-auto">
          <div className="flex items-center justify-between text-xs text-gray-500 px-1">
            <span>文件列表({fileStatuses.length})</span>
            {!uploading && (
              <button
                onClick={clearList}
                className="text-gray-400 hover:text-gray-600 flex items-center gap-1"
              >
                <X className="w-3 h-3" /> 清空
              </button>
            )}
          </div>
          {fileStatuses.map((f, idx) => (
            <div
              key={idx}
              className="flex items-center gap-2 px-2 py-1.5 bg-gray-50 rounded-md text-xs"
            >
              <div className="flex-shrink-0">
                {f.status === "done" ? (
                  <CheckCircle className="w-4 h-4 text-green-500" />
                ) : f.status === "failed" ? (
                  <AlertCircle className="w-4 h-4 text-red-500" />
                ) : f.status === "uploading" ? (
                  <FileUp className="w-4 h-4 text-foxAmber animate-pulse" />
                ) : (
                  <div className="w-4 h-4 rounded-full bg-gray-300" />
                )}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-gray-700">{f.name}</span>
                  <span className="text-gray-400 flex-shrink-0">{formatSize(f.size)}</span>
                </div>
                {f.status === "uploading" && (
                  <div className="w-full bg-gray-200 rounded-full h-1 mt-1">
                    <div
                      className="bg-foxAmber h-1 rounded-full transition-all duration-300"
                      style={{ width: `${f.progress}%` }}
                    />
                  </div>
                )}
                {f.status === "failed" && (
                  <div className="text-red-500 mt-0.5">上传失败</div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {(batchError || error) && (
        <div className="flex items-center gap-2 text-sm text-red-500 mt-2">
          <AlertCircle className="w-4 h-4" />
          <span>{batchError || error}</span>
        </div>
      )}
    </div>
  );
}
