"""从解析后的 chunks 构建 DMAP(文档结构图)。

输入: docling_chunks = [{text, heading, level, page}, ...]
输出: DMAP(course_id, root_node_tree)

设计原则:
- 简单可靠 > 聪明脆弱。不做"图 caption 就近挂 paragraph"那种易错逻辑。
- heading 1-2 视为 chapter;heading 3+ 视为 section;无 heading 视为根目录的 paragraph。
- 跨节引用靠"第X章"正则匹配,其他类型显式 ignore(不发明)。
- 输入坏掉就抛异常,让上层决定。
"""

from __future__ import annotations

import hashlib
import re
from typing import Iterable

from app.schemas.foxsay import (
    DMAP,
    DMAPCrossRef,
    DMAPElement,
    DMAPNode,
)

# 中文章序: "第一章" / "第二章" / "第3章" / "第10章" / "第十一章"
_CHAPTER_REF_RE = re.compile(r"第([一二三四五六七八九十百千零〇\d]+)章")


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _chinese_to_int(s: str) -> int | None:
    """把中文数字 / 阿拉伯数字都转成 int。失败返回 None。"""
    if s.isdigit():
        return int(s)
    mapping = {
        "零": 0, "〇": 0,
        "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
        "六": 6, "七": 7, "八": 8, "九": 9,
    }
    if s in mapping:
        return mapping[s]
    if s == "十":
        return 10
    if s.startswith("十") and len(s) > 1 and s[1] in mapping:
        return 10 + mapping[s[1]]
    if len(s) == 2 and s[0] in mapping and s[1] == "十":
        return mapping[s[0]] * 10
    if len(s) == 3 and s[1] == "十" and s[2] in mapping:
        return mapping[s[0]] * 10 + mapping[s[2]]
    return None


def _chapter_id(n: int) -> str:
    return f"ch-{n}"


def _parse_chapter_number(title: str) -> int | None:
    """从章节标题里提取"第N章"的 N,失败返回 None。

    例如 "第三章" / "第3章" / "第三章 积分" → 3。
    """
    if not title:
        return None
    m = _CHAPTER_REF_RE.search(title)
    if m is None:
        return None
    return _chinese_to_int(m.group(1))


def _detect_kind(text: str) -> str:
    """粗粒度: paragraph / formula / figure。"""
    stripped = text.strip()
    if stripped.startswith("$$") or stripped.startswith("$") or "=" in stripped and "\\" in stripped:
        return "formula"
    if stripped.startswith("![") or stripped.lower().startswith("figure") or stripped.startswith("图"):
        return "figure"
    return "paragraph"


def _make_element(chunk: dict, idx: int) -> DMAPElement:
    text = str(chunk.get("text", ""))
    kind = _detect_kind(text)
    el = DMAPElement(
        type=kind,
        id=f"el-{idx:04d}",
        text_preview=text[:120],
        page_ref=str(chunk.get("page", "")) if chunk.get("page") is not None else "",
    )
    if kind == "formula":
        el.latex = text
    if kind == "figure":
        el.caption = text
    return el


def build_dmap(
    course_id: str,
    docling_chunks: Iterable[dict],
    source_file: str = "",
) -> DMAP:
    """从 docling_chunks 构造 DMAP。

    算法:
    1. 维护一个 chapter/section 栈(level 决定层级)。
    2. heading 出现时压栈 / 弹栈。
    3. 非 heading chunk 全部转成 element,挂到当前叶节点。
    4. 根节点是"course",id = course_id,无 title 重复;若没有任何 chapter,
       把所有 element 挂到根节点 children 的一个虚拟 section "ch-0" 下。
    """
    if not course_id or not course_id.strip():
        raise ValueError("course_id is required to build DMAP")

    chunks = list(docling_chunks)
    for i, c in enumerate(chunks):
        if not isinstance(c, dict):
            raise TypeError(f"chunk #{i} is not a dict: {type(c).__name__}")
        if "text" not in c:
            raise ValueError(f"chunk #{i} missing 'text' field")

    # 根节点: course
    root = DMAPNode(
        type="course",
        id=course_id,
        title=source_file or course_id,
        source_file=source_file,
    )

    # chapter 计数器 — 用来生成 ch-N
    chapter_counter = 0
    # 当前节点栈:[(node, level)],level 越大越深
    stack: list[tuple[DMAPNode, int]] = [(root, 0)]

    el_idx = 0
    chapter_titles: dict[int, str] = {}  # ch-N -> title,用于 cross_ref 解析

    for chunk in chunks:
        heading = str(chunk.get("heading", "")).strip()
        level = int(chunk.get("level", 0) or 0)
        text = str(chunk.get("text", "")).strip()
        if not text and not heading:
            continue

        if heading and level > 0:
            # 弹栈直到找到 level 严格小于当前 heading 的父节点
            while stack and stack[-1][1] >= level:
                stack.pop()
            parent = stack[-1][0] if stack else root

            if level == 1:
                chapter_counter += 1
                # 优先从标题里抽 "第N章" 数字,这样 "第三章" → ch-3
                title_num = _parse_chapter_number(heading)
                ch_id = _chapter_id(title_num) if title_num is not None else _chapter_id(chapter_counter)
                chapter_titles[title_num or chapter_counter] = heading
                node = DMAPNode(
                    type="chapter",
                    id=ch_id,
                    title=heading,
                    source_file=source_file,
                    content_hash=_hash_text(heading),
                )
            else:
                # section id 在 chapter id 后面追加 .s-N
                parent_id = parent.id
                section_idx = sum(1 for c in parent.children if c.type == "section") + 1
                node = DMAPNode(
                    type="section",
                    id=f"{parent_id}.s-{section_idx}",
                    title=heading,
                    source_file=source_file,
                    content_hash=_hash_text(heading),
                )

            parent.children.append(node)
            stack.append((node, level))
            continue

        # 非 heading chunk → element,挂到当前叶节点
        if text:
            leaf = stack[-1][0] if stack else root
            el = _make_element(chunk, el_idx)
            el_idx += 1
            leaf.elements.append(el)

    # 没有任何 chapter 时,把全部 elements 挂到一个默认 ch-0 节点
    if chapter_counter == 0 and el_idx > 0:
        default_ch = DMAPNode(
            type="chapter",
            id="ch-0",
            title="(未分章)",
            source_file=source_file,
            content_hash=_hash_text("ch-0"),
        )
        default_ch.elements = list(root.elements)
        root.children.append(default_ch)
        root.elements = []
        chapter_titles[0] = "(未分章)"

    # 计算每节点的 content_hash (heading + elements text)
    def _recompute_hash(node: DMAPNode) -> str:
        parts = [node.title or node.id]
        for el in node.elements:
            parts.append(el.text_preview)
        for child in node.children:
            parts.append(_recompute_hash(child))
        node.content_hash = _hash_text("\n".join(parts))
        return node.content_hash

    _recompute_hash(root)

    dmap = DMAP(course_id=course_id, root=root)

    # 一次性提取跨节引用
    dmap.root = extract_cross_refs(dmap.root, chapter_titles)

    return dmap


def extract_cross_refs(
    root_node: DMAPNode,
    chapter_titles: dict[int, str] | None = None,
) -> DMAPNode:
    """扫描所有 element text_preview,匹配"第X章"等跨节引用,挂到对应 node.cross_refs。

    只识别章节级("第X章"),section/figure 级不识别 — 不发明脆弱的规则。
    """
    # 先建 ch-N → node 索引(只对 type=chapter 的一级子节点)
    if chapter_titles is None:
        chapter_titles = {}
    ch_index: dict[int, DMAPNode] = {}
    for i, child in enumerate(root_node.children, start=1):
        if child.type == "chapter" and child.id.startswith("ch-"):
            try:
                num = int(child.id.split("-", 1)[1])
            except (ValueError, IndexError):
                continue
            ch_index[num] = child
            chapter_titles.setdefault(num, child.title)

    def _walk(node: DMAPNode) -> None:
        # 收集本节点 elements 里的 cross_refs(只算本节点的,不算子节点)
        own_refs: list[DMAPCrossRef] = []
        for el in node.elements:
            for m in _CHAPTER_REF_RE.finditer(el.text_preview):
                num = _chinese_to_int(m.group(1))
                if num is None or num not in ch_index:
                    continue
                target = ch_index[num]
                if target.id == node.id or _is_descendant(target, node):
                    continue
                ref = DMAPCrossRef(target_id=target.id, relation=f"refers-to-chapter-{num}")
                if ref not in own_refs:
                    own_refs.append(ref)
        node.cross_refs = own_refs
        for child in node.children:
            _walk(child)

    _walk(root_node)
    return root_node


def _is_descendant(maybe_ancestor: DMAPNode, node: DMAPNode) -> bool:
    for c in maybe_ancestor.children:
        if c.id == node.id:
            return True
        if _is_descendant(c, node):
            return True
    return False
