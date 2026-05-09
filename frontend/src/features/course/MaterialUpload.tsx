import { useRef, useState } from "react";
import { Upload, FileUp, AlertCircle, CheckCircle } from "lucide-react";
import { useUploadMaterial } from "./useMaterials";

const ACCEPTED = ".pdf,.ppt,.pptx,.png,.jpg,.txt";

interface MaterialUploadProps {
  courseId: string;
  onUploaded: () => void;
}

export default function MaterialUpload({ courseId, onUploaded }: MaterialUploadProps) {
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const { upload, uploading, progress, error } = useUploadMaterial(courseId);
  const [success, setSuccess] = useState(false);

  const handleFiles = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    const file = files[0];
    try {
      setSuccess(false);
      await upload(file);
      setSuccess(true);
      onUploaded();
      setTimeout(() => setSuccess(false), 3000);
    } catch {}
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    handleFiles(e.dataTransfer.files);
  };

  return (
    <div className="mb-6">
      <div
        onDrop={handleDrop}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onClick={() => inputRef.current?.click()}
        className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all ${
          dragOver ? "border-foxAmber bg-foxAmber/5" : "border-gray-300 hover:border-foxAmber"
        } ${uploading ? "pointer-events-none opacity-60" : ""}`}
      >
        {uploading ? (
          <div className="space-y-3">
            <FileUp className="w-10 h-10 text-foxAmber mx-auto animate-bounce" />
            <p className="text-sm text-gray-600">上传中... {progress}%</p>
            <div className="w-full bg-gray-200 rounded-full h-2">
              <div
                className="bg-foxAmber h-2 rounded-full transition-all duration-300"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>
        ) : success ? (
          <div className="space-y-2">
            <CheckCircle className="w-10 h-10 text-green-500 mx-auto" />
            <p className="text-sm text-green-600">上传成功!</p>
          </div>
        ) : (
          <>
            <Upload className="w-10 h-10 text-gray-400 mx-auto mb-3" />
            <p className="text-sm text-gray-500 mb-1">拖拽文件到此处，或点击选择</p>
            <p className="text-xs text-gray-400">支持 PDF、PPT、图片、文本文件</p>
          </>
        )}
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED}
          onChange={(e) => handleFiles(e.target.files)}
          className="hidden"
        />
      </div>

      {error && (
        <div className="flex items-center gap-2 text-sm text-red-500 mt-2">
          <AlertCircle className="w-4 h-4" />
          <span>{error}</span>
        </div>
      )}
    </div>
  );
}
