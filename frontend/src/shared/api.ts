export const API_BASE = "/api";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    throw new Error(`API error: ${res.status}`);
  }
  return res.json();
}

/**
 * 带真实上传进度的 FormData POST。
 * 用 XMLHttpRequest 实现(fetch 不支持上传进度),不引入 axios 依赖(HEC-4)。
 * onProgress 回调在浏览器每次刷新上传进度时触发,progress 为 0-100 整数。
 */
function uploadWithProgress<T>(
  path: string,
  formData: FormData,
  onProgress?: (progress: number) => void,
): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE}${path}`);
    // 不要手动设 Content-Type,让浏览器自动加 multipart boundary
    if (onProgress) {
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) {
          onProgress(Math.round((e.loaded / e.total) * 100));
        }
      };
    }
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText) as T);
        } catch (e) {
          reject(new Error(`Failed to parse response: ${e}`));
        }
      } else {
        let detail = `API error: ${xhr.status}`;
        try {
          const body = JSON.parse(xhr.responseText);
          if (body?.detail) detail = `${detail}: ${body.detail}`;
        } catch {
          // ignore parse error
        }
        reject(new Error(detail));
      }
    };
    xhr.onerror = () => reject(new Error("Network error during upload"));
    xhr.send(formData);
  });
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: JSON.stringify(body ?? {}) }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PUT", body: JSON.stringify(body ?? {}) }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PATCH", body: JSON.stringify(body ?? {}) }),
  del: <T>(path: string) =>
    request<T>(path, { method: "DELETE" }),
  upload: <T>(path: string, formData: FormData) =>
    request<T>(path, { method: "POST", headers: {}, body: formData }),
  uploadWithProgress: <T>(path: string, formData: FormData, onProgress?: (p: number) => void) =>
    uploadWithProgress<T>(path, formData, onProgress),
};
