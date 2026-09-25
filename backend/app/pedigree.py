"""谱系图校验与回溯：用 NetworkX 有向图保证材料不会成为自己的祖先。"""
import networkx as nx
from sqlalchemy.orm import Session

from .models import CrossEvent, Material


def build_pedigree_graph(db: Session) -> nx.DiGraph:
    """从数据库载入全部 亲本 -> 后代 有向边（未知亲本不产生边）。"""
    g = nx.DiGraph()
    g.add_nodes_from(m.id for m in db.query(Material.id))
    for ev in db.query(CrossEvent).all():
        for parent_id in (ev.parent_a_id, ev.parent_b_id):
            if parent_id is None:
                continue
            for child in ev.offspring:
                g.add_edge(parent_id, child.id)
    return g


def validate_new_edges(
    db: Session, parent_ids: list[int | None], offspring_ids: list[int]
) -> None:
    """校验新增 亲本->后代 边。若某后代已是某亲本的祖先（会形成环），抛 ValueError。"""
    g = build_pedigree_graph(db)
    for parent_id in parent_ids:
        if parent_id is None:
            continue
        for child_id in offspring_ids:
            if parent_id == child_id:
                raise ValueError(
                    f"材料 #{child_id} 不能作为自己的亲本"
                )
            if nx.has_path(g, child_id, parent_id):
                raise ValueError(
                    f"禁止登记：材料 #{parent_id} 是材料 #{child_id} 的后代，"
                    "该关系会让材料成为自己的祖先"
                )


def ancestor_ids(db: Session, material_id: int) -> set[int]:
    """返回材料的全部祖先 id（沿 亲本->后代 图反向遍历）。"""
    g = build_pedigree_graph(db)
    if material_id not in g:
        return set()
    return nx.ancestors(g, material_id)
