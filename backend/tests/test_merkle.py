"""Merkle Tree 计算与 diff 测试。"""

import pytest

from app.services.dmap import build_dmap
from app.services.merkle import compute_merkle_tree, diff_merkle_trees


def _make_dmap():
    chunks = [
        {"text": "第一章 A", "heading": "第一章", "level": 1, "page": 1},
        {"text": "A 的内容。", "heading": "第一章", "level": 0, "page": 1},
        {"text": "第二章 B", "heading": "第二章", "level": 1, "page": 5},
        {"text": "B 的内容。", "heading": "第二章", "level": 0, "page": 5},
    ]
    return build_dmap("course-merkle", chunks)


def test_compute_merkle_tree():
    """相同 DMAP → root_hash 稳定。"""
    dmap1 = _make_dmap()
    dmap2 = _make_dmap()
    tree1 = compute_merkle_tree(dmap1)
    tree2 = compute_merkle_tree(dmap2)

    assert tree1.root_hash == tree2.root_hash
    assert tree1.root_hash != ""
    # 应该有 root + 2 chapter = 3 个 node
    assert len(tree1.nodes) == 3


def test_diff_merkle_trees():
    """修改一个节点,验证 diff 包含该节点。"""
    dmap_old = _make_dmap()
    tree_old = compute_merkle_tree(dmap_old)

    # 修改:在 ch-2 加一个新 element
    dmap_new = _make_dmap()
    ch2 = dmap_new.root.children[1]
    ch2.elements.append(
        type(ch2.elements[0])(
            type="paragraph",
            id="el-9999",
            text_preview="新增内容",
            page_ref="6",
        )
    )
    # 重新计算 hash
    from app.services.dmap import _hash_text
    import hashlib

    def _rehash(node):
        parts = [node.title or node.id]
        for el in node.elements:
            parts.append(el.text_preview)
        for c in node.children:
            parts.append(_rehash(c))
        node.content_hash = hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:16]
        return node.content_hash

    _rehash(dmap_new.root)
    tree_new = compute_merkle_tree(dmap_new)

    changed = diff_merkle_trees(tree_old, tree_new)
    # ch-2 的 hash 变了,root 因为 children hash 变了也跟着变
    assert "ch-2" in changed
    assert dmap_new.root.id in changed  # course 根节点


def test_diff_merkle_trees_no_old_returns_all():
    """old_tree=None → 返回 new_tree 的全部 node_id(全量重算语义)。"""
    dmap = _make_dmap()
    tree = compute_merkle_tree(dmap)
    changed = diff_merkle_trees(None, tree)
    assert set(changed) == {n.node_id for n in tree.nodes}
