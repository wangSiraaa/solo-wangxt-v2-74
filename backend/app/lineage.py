"""Pedigree graph logic built on NetworkX.

Nodes are material ids.  An edge ``parent -> child`` means the parent
contributes to the child.  Selfing adds no edge (a node cannot be its
own ancestor).  Registering a mating is rejected when:

* the child would become its own ancestor (cycle / material-is-own-ancestor),
* a missing required parent is supplied,
* cross parents are identical.
"""
from __future__ import annotations

import networkx as nx
from sqlalchemy.orm import Session

from .db import Material, MatingEvent


class PedigreeError(ValueError):
    """Raised when a mating event violates pedigree constraints."""


def build_graph(db: Session) -> nx.DiGraph:
    """Build the parent -> child directed graph from stored mating events."""
    g = nx.DiGraph()
    for m in db.query(Material).all():
        g.add_node(m.id)
    for ev in db.query(MatingEvent).all():
        child_ids = [c.id for c in ev.progeny]
        parents = [p for p in (ev.parent_a_id, ev.parent_b_id) if p is not None]
        for pid in parents:
            g.add_node(pid)
            for cid in child_ids:
                if pid != cid:  # selfing is not an ancestry edge
                    g.add_edge(pid, cid)
    return g


def validate_mating(
    db: Session,
    *,
    cross_type: str,
    parent_a_id: int | None,
    parent_b_id: int | None,
    child_ids: list[int] | None = None,
    exclude_event_id: int | None = None,
) -> nx.DiGraph:
    """Validate a mating event and return the graph including its new edges.

    ``child_ids`` are the progeny already linked to an existing event when
    editing; for new events they are usually empty (the child material is
    created together with the event in one transaction, so edges appear on
    later loads).  Validation of parent-only edges with the future child
    happens in :func:`validate_new_cross` instead.
    """
    if cross_type not in ("self", "cross", "open"):
        raise PedigreeError(f"未知交配类型: {cross_type}")

    for pid in (parent_a_id, parent_b_id):
        if pid is not None and db.get(Material, pid) is None:
            raise PedigreeError(f"亲本 {pid} 不存在")

    if cross_type == "self":
        if parent_a_id is None:
            raise PedigreeError("自交必须登记一个亲本")
        if parent_b_id is not None:
            raise PedigreeError("自交只能有一个亲本")
    elif cross_type == "cross":
        if parent_a_id is None or parent_b_id is None:
            raise PedigreeError("杂交必须登记两个亲本，未知请改用 open")
        if parent_a_id == parent_b_id:
            raise PedigreeError("杂交的两个亲本必须不同")

    g = build_graph(db)
    if exclude_event_id is not None:
        # Remove edges contributed by the event being edited.
        ev = db.get(MatingEvent, exclude_event_id)
        if ev is not None:
            old_parents = [p for p in (ev.parent_a_id, ev.parent_b_id) if p]
            for c in ev.progeny:
                for p in old_parents:
                    if g.has_edge(p, c.id):
                        g.remove_edge(p, c.id)

    # Provisional edges for the event under validation.
    parents = [p for p in (parent_a_id, parent_b_id) if p is not None]
    for cid in child_ids or []:
        g.add_node(cid)
        for pid in parents:
            if pid != cid:
                g.add_edge(pid, cid)

    if not nx.is_directed_acyclic_graph(g):
        cycle = nx.find_cycle(g)
        raise PedigreeError(
            f"禁止材料成为自己的祖先: 检测到关系环 {' -> '.join(str(e[0]) for e in cycle)}"
        )
    return g


def validate_new_cross(
    db: Session,
    *,
    cross_type: str,
    parent_a_id: int | None,
    parent_b_id: int | None,
    child_id: int,
) -> None:
    """Full validation when a child material is created with its mating event."""
    g = validate_mating(
        db,
        cross_type=cross_type,
        parent_a_id=parent_a_id,
        parent_b_id=parent_b_id,
        child_ids=[child_id],
    )
    # Direct self-ancestry guard beyond the cycle check (covers A x A style).
    parents = {p for p in (parent_a_id, parent_b_id) if p is not None}
    if child_id in parents:
        raise PedigreeError("禁止材料成为自己的祖先: 后代与亲本相同")
    if child_id in nx.ancestors(g, child_id):
        raise PedigreeError("禁止材料成为自己的祖先")


def ancestry(db: Session, material_id: int) -> dict:
    """Return parents, ancestors by generation depth and the mating origin."""
    g = build_graph(db)
    if material_id not in g:
        return {"ancestors": [], "parents": [], "event": None}
    ancestors = sorted(nx.ancestors(g, material_id))
    parents = sorted(g.predecessors(material_id))
    mat = db.get(Material, material_id)
    event = mat.mating_event if mat else None
    return {"ancestors": ancestors, "parents": parents, "event_id": event.id if event else None}


def descendants(db: Session, material_id: int) -> list[int]:
    g = build_graph(db)
    return sorted(nx.descendants(g, material_id)) if material_id in g else []
