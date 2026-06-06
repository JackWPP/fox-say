"""从 DMAP 计算 Merkle Tree,支持增量 diff。

纯 Python 实现,无外部依赖。
"""

from __future__ import annotations

import hashlib

from app.schemas.foxsay import DMAP, DMAPNode, MerkleTree, MerkleTreeNode


def _hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def _walk(node: DMAPNode, nodes_out: list[MerkleTreeNode]) -> MerkleTreeNode:
    """递归遍历 DMAP,产生 MerkleTreeNode 列表。"""
    children_hashes: list[str] = []
    child_merkle_nodes: list[MerkleTreeNode] = []
    for child in node.children:
        cmn = _walk(child, nodes_out)
        child_merkle_nodes.append(cmn)
        children_hashes.append(cmn.content_hash)

    # 节点自身的 hash = sha256(content_hash + join(children_hashes))[:16]
    payload = node.content_hash + "|" + ",".join(children_hashes)
    h = _hash(payload)

    mtn = MerkleTreeNode(
        node_id=node.id,
        content_hash=h,
        children_hashes=children_hashes,
    )
    nodes_out.append(mtn)
    return mtn


def compute_merkle_tree(dmap: DMAP) -> MerkleTree:
    """从 DMAP 构造 MerkleTree。

    每个 DMAPNode 对应一个 MerkleTreeNode(扁平化存)。
    root_hash 是根 DMAPNode 对应的 MerkleTreeNode.content_hash。
    """
    if dmap is None:
        raise ValueError("dmap is required")
    if dmap.root is None:
        raise ValueError("dmap.root is None")

    nodes: list[MerkleTreeNode] = []
    root_mtn = _walk(dmap.root, nodes)
    return MerkleTree(
        course_id=dmap.course_id,
        root_hash=root_mtn.content_hash,
        nodes=nodes,
    )


def diff_merkle_trees(
    old_tree: MerkleTree | None,
    new_tree: MerkleTree,
) -> list[str]:
    """比较 old vs new,返回 content_hash 变化的 node_id 列表。

    - old_tree 为 None → 返回 new_tree 的所有 node_id(全量重算)。
    - 否则按 node_id 配对,content_hash 不同的视为变化。
    """
    if old_tree is None:
        return [n.node_id for n in new_tree.nodes]

    old_map: dict[str, str] = {n.node_id: n.content_hash for n in old_tree.nodes}
    changed: list[str] = []
    for n in new_tree.nodes:
        prev = old_map.get(n.node_id)
        if prev != n.content_hash:
            changed.append(n.node_id)
    return changed
