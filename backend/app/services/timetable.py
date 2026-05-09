import csv
import io

TITLE_ALIASES = {"课程名", "课程", "名称", "title", "course", "name"}
TEACHER_ALIASES = {"教师", "老师", "teacher", "instructor"}
EXAM_DATE_ALIASES = {"考试日期", "考试时间", "exam_date", "exam date", "examdate"}


def _find_column(headers: list[str], aliases: set[str]) -> str | None:
    for h in headers:
        if h.strip().lower() in aliases:
            return h
    return None


def parse_csv(content: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(content))
    headers = list(reader.fieldnames or [])
    title_col = _find_column(headers, TITLE_ALIASES)
    if title_col is None:
        raise ValueError("CSV 缺少课程名列（课程名/课程/名称/title）")
    teacher_col = _find_column(headers, TEACHER_ALIASES)
    exam_date_col = _find_column(headers, EXAM_DATE_ALIASES)

    rows: list[dict] = []
    for row in reader:
        title = row.get(title_col, "").strip()
        if not title:
            continue
        teacher = row[teacher_col].strip() if teacher_col and row.get(teacher_col) else None
        exam_date = row[exam_date_col].strip() if exam_date_col and row.get(exam_date_col) else None
        rows.append({"title": title, "teacher": teacher, "exam_date": exam_date})
    return rows
