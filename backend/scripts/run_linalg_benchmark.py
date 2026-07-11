"""
线性代数标杆课材料处理脚本。
用法: uv run python scripts/run_linalg_benchmark.py
在 backend/ 目录下运行。
"""
import os
import sys
import time
import json
import httpx
from pathlib import Path

API = "http://localhost:8000"
COURSE_TITLE = "线性代数-demo"
COURSE_DESCRIPTION = "线性代数标杆课（demo）- 向量空间、矩阵、特征值、方程组、特征理论"

# 材料目录 - 从 tmp_upload 中找到线代相关文件
MATERIAL_DIRS = [
    Path("D:/fox-say/tmp_upload/线代课件/课件"),
    Path("D:/fox-say/tmp_upload/线代课堂资料/课堂资料"),
]


def create_course():
    """创建线性代数课程"""
    resp = httpx.post(f"{API}/courses", json={
        "title": COURSE_TITLE,
        "description": COURSE_DESCRIPTION,
    }, timeout=30)
    resp.raise_for_status()
    course = resp.json()
    print(f"[OK] 课程已创建: id={course['id']}, title={course['title']}")
    return course["id"]


def upload_material(course_id: str, file_path: Path):
    """上传单个材料"""
    with open(file_path, "rb") as f:
        files = {"file": (file_path.name, f, "application/octet-stream")}
        resp = httpx.post(
            f"{API}/courses/{course_id}/materials",
            files=files,
            timeout=120,
        )
    if resp.status_code >= 400:
        print(f"  [ERROR] {file_path.name}: {resp.status_code} {resp.text[:200]}")
        return None
    result = resp.json()
    print(f"  [OK] {file_path.name} -> material_id={result.get('id')}, status={result.get('status')}")
    return result


def get_knowledge_status(course_id: str):
    """获取知识构建状态"""
    resp = httpx.get(f"{API}/courses/{course_id}/knowledge-status", timeout=15)
    resp.raise_for_status()
    return resp.json()


def get_course_outline(course_id: str):
    """获取课程大纲"""
    try:
        resp = httpx.get(f"{API}/courses/{course_id}/course-outline", timeout=15)
        if resp.status_code == 200:
            return resp.json()
        return None
    except Exception:
        return None


def wait_for_completion(course_id: str, max_wait_seconds: int = 1800):
    """等待知识构建完成（最多 30 分钟）"""
    start = time.time()
    last_status = None

    while time.time() - start < max_wait_seconds:
        try:
            status = get_knowledge_status(course_id)
        except Exception as e:
            print(f"[WARN] 状态查询失败: {e}")
            time.sleep(10)
            continue

        elapsed = int(time.time() - start)

        # 打印状态变化
        source_status = status.get("source_status", "unknown")
        projection_status = status.get("projection_status", "unknown")
        materials = status.get("materials", [])
        fragment_count = status.get("coverage", {}).get("fragment_count", 0)
        semantic_status = status.get("semantic_status", "not_started")
        term_count = status.get("coverage", {}).get("term_count", 0)
        kc_count = status.get("coverage", {}).get("kc_count", 0)
        relation_count = status.get("coverage", {}).get("kc_relation_count", 0)

        status_str = (
            f"  [{elapsed}s] source={source_status} projection={projection_status} "
            f"semantic={semantic_status} | fragments={fragment_count} "
            f"terms={term_count} kcs={kc_count} relations={relation_count}"
        )

        for m in materials:
            m_status = m.get("status", "?")
            m_name = m.get("file_name", "?")[:30]
            status_str += f"\n    {m_name}: {m_status}"

        if status_str != last_status:
            print(status_str)
            last_status = status_str

        # 检查是否完成
        all_ready = (
            source_status in ("ready", "partial")
            and projection_status in ("ready", "stale")
            and all(m.get("status") in ("ready", "failed") for m in materials)
        )

        if all_ready:
            print(f"\n[OK] 知识构建完成! 耗时 {elapsed}s")
            outline = get_course_outline(course_id)
            if outline:
                sections = outline.get("sections", [])
                print(f"  CourseOutline: {len(sections)} sections")
                for s in sections[:10]:
                    print(f"    - {s.get('title', '?')}")
            return status

        time.sleep(5)

    print(f"\n[TIMEOUT] 等待超时 ({max_wait_seconds}s)")
    return last_status


def main():
    # 收集所有材料文件
    all_files = []
    for d in MATERIAL_DIRS:
        if d.exists():
            for f in d.iterdir():
                if f.is_file() and f.suffix.lower() in (".pdf", ".ppt", ".pptx", ".doc", ".docx"):
                    all_files.append(f)
        else:
            # 尝试列出目录内容以排查路径问题
            parent = d.parent
            if parent.exists():
                print(f"[INFO] {d} 不存在, 父目录内容:")
                for child in parent.iterdir():
                    print(f"  {child.name}")
            else:
                print(f"[WARN] 父目录不存在: {parent}")

    if not all_files:
        print("[ERROR] 没有找到材料文件!")
        # 尝试列出 tmp_upload 下的所有目录
        tmp = Path("D:/fox-say/tmp_upload")
        if tmp.exists():
            print(f"[INFO] tmp_upload 内容:")
            for child in sorted(tmp.iterdir()):
                if child.is_dir():
                    print(f"  [DIR] {child.name}")
                    for sub in child.iterdir():
                        if sub.is_dir():
                            print(f"    [DIR] {sub.name}")
                            for f in sub.iterdir():
                                if f.is_file():
                                    print(f"      {f.name} ({f.stat().st_size} bytes)")
                        elif sub.is_file():
                            print(f"    {sub.name} ({sub.stat().st_size} bytes)")
        sys.exit(1)

    print(f"[INFO] 找到 {len(all_files)} 个材料文件:")
    for f in all_files:
        print(f"  - {f.name} ({f.stat().st_size // 1024} KB)")

    # 创建课程
    course_id = create_course()

    # 上传所有材料
    print(f"\n[INFO] 开始上传 {len(all_files)} 个材料到课程 {course_id}...")
    for f in all_files:
        print(f"  上传: {f.name}")
        upload_material(course_id, f)
        time.sleep(1)  # 避免过快

    # 等待知识构建完成
    print(f"\n[INFO] 等待知识构建管线完成...")
    final_status = wait_for_completion(course_id, max_wait_seconds=1800)

    if final_status:
        print("\n[INFO] 最终状态:")
        print(json.dumps(final_status, ensure_ascii=False, indent=2))

    print(f"\n[DONE] 课程 ID: {course_id}")
    print(f"  知识状态 API: {API}/courses/{course_id}/knowledge-status")
    print(f"  课程大纲 API: {API}/courses/{course_id}/course-outline")


if __name__ == "__main__":
    main()
