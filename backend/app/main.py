"""FastAPI application: breeding records, NetworkX pedigree validation,
PostgreSQL persistence, family means, and static React build hosting.
"""
from __future__ import annotations

import os

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from . import lineage
from .db import (
    Material,
    MatingEvent,
    Observation,
    Plot,
    SessionLocal,
    Trait,
    get_db,
    init_schema,
)
from .schemas import (
    FamilyMeanItem,
    FamilyMeanResponse,
    MaterialCreate,
    MaterialDetail,
    MaterialOut,
    MatingAttachProgeny,
    MatingCreate,
    MatingEventOut,
    ObservationOut,
    ObservationUpsert,
    PlotOut,
    TraitOut,
)

app = FastAPI(title="虚构作物育种管理 API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def next_code(db: Session, prefix: str) -> str:
    klass = Material if prefix == "M" else MatingEvent
    n = db.query(func.count(klass.id)).scalar() or 0
    return f"{prefix}-{n + 1:04d}"


def obs_to_out(o: Observation) -> ObservationOut:
    return ObservationOut(
        id=o.id,
        material_id=o.material_id,
        trait_id=o.trait_id,
        status=o.status,
        value=float(o.value) if o.value is not None else None,
        observed_on=o.observed_on,
        recorded_at=o.recorded_at,
        source_note=o.source_note,
        trait_code=o.trait.trait_code,
        trait_name=o.trait.name,
        unit=o.trait.unit,
    )


def plot_to_out(p: Plot) -> PlotOut:
    return PlotOut(
        id=p.id,
        plot_code=p.plot_code,
        block=p.block,
        position=p.position,
        material_id=p.material_id,
        material_code=p.material.code if p.material else None,
        material_name=p.material.name if p.material else None,
        generation=p.material.generation if p.material else None,
    )


@app.on_event("startup")
def _startup() -> None:
    init_schema()


@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    db.execute(select(1))
    return {"status": "ok", "storage": "postgresql"}


# ---------------- Materials ----------------

@app.get("/api/materials", response_model=list[MaterialOut])
def list_materials(q: str | None = None, db: Session = Depends(get_db)):
    stmt = select(Material).order_by(Material.id)
    if q:
        stmt = stmt.where(Material.name.ilike(f"%{q}%"))
    return db.scalars(stmt).all()


@app.get("/api/materials/{material_id}", response_model=MaterialDetail)
def get_material(material_id: int, db: Session = Depends(get_db)):
    m = db.get(
        Material,
        material_id,
        options=[joinedload(Material.mating_event).joinedload(MatingEvent.parent_a),
                 joinedload(Material.mating_event).joinedload(MatingEvent.parent_b)],
    )
    if m is None:
        raise HTTPException(404, "材料不存在")

    out = MaterialDetail.model_validate(m)
    info = lineage.ancestry(db, m.id)
    out.ancestor_ids = info["ancestors"]
    out.descendant_ids = lineage.descendants(db, m.id)
    obs = (
        db.query(Observation)
        .options(joinedload(Observation.trait))
        .filter_by(material_id=m.id)
        .order_by(Observation.trait_id)
        .all()
    )
    out.observations = [obs_to_out(o) for o in obs]
    plots = db.query(Plot).filter_by(material_id=m.id).all()
    out.plots = [plot_to_out(p) for p in plots]
    return out


@app.post("/api/materials", response_model=MaterialOut, status_code=201)
def create_material(payload: MaterialCreate, db: Session = Depends(get_db)):
    """Register a material; optionally with its mating origin in one call."""
    event: MatingEvent | None = None
    if payload.cross_type is not None:
        try:
            lineage.validate_mating(
                db,
                cross_type=payload.cross_type,
                parent_a_id=payload.parent_a_id,
                parent_b_id=payload.parent_b_id,
                child_ids=[],
            )
        except lineage.PedigreeError as e:
            raise HTTPException(422, str(e))
        event = MatingEvent(
            event_code=next_code(db, "X"),
            event_date=payload.event_date,
            cross_type=payload.cross_type,
            parent_a_id=payload.parent_a_id,
            parent_b_id=payload.parent_b_id,
            notes="随材料登记创建的交配事件",
        )
        db.add(event)
        db.flush()

    m = Material(
        code=next_code(db, "M"),
        name=payload.name,
        generation=payload.generation,
        notes=payload.notes,
        mating_event=event,
    )
    db.add(m)
    try:
        db.flush()  # assign m.id before graph validation
        if event is not None:
            lineage.validate_new_cross(
                db,
                cross_type=event.cross_type,
                parent_a_id=event.parent_a_id,
                parent_b_id=event.parent_b_id,
                child_id=m.id,
            )
        db.commit()
    except lineage.PedigreeError as e:
        db.rollback()
        raise HTTPException(422, str(e))
    except Exception:
        db.rollback()
        raise
    db.refresh(m)
    return m


# ---------------- Mating events ----------------

@app.get("/api/matings", response_model=list[MatingEventOut])
def list_matings(db: Session = Depends(get_db)):
    events = (
        db.query(MatingEvent)
        .options(joinedload(MatingEvent.parent_a), joinedload(MatingEvent.parent_b))
        .order_by(MatingEvent.id)
        .all()
    )
    return events


@app.post("/api/matings", response_model=MatingEventOut, status_code=201)
def create_mating(payload: MatingCreate, db: Session = Depends(get_db)):
    """Register a selfing or two-parent cross (or open event), plus progeny."""
    # Validate parent rules before any INSERT (a DB CHECK otherwise raises 500).
    try:
        lineage.validate_mating(
            db,
            cross_type=payload.cross_type,
            parent_a_id=payload.parent_a_id,
            parent_b_id=payload.parent_b_id,
            child_ids=[],
        )
    except lineage.PedigreeError as e:
        raise HTTPException(422, str(e))

    event = MatingEvent(
        event_code=next_code(db, "X"),
        event_date=payload.event_date,
        cross_type=payload.cross_type,
        parent_a_id=payload.parent_a_id,
        parent_b_id=payload.parent_b_id,
        notes=payload.notes,
    )
    db.add(event)
    try:
        db.flush()
        gen = payload.progeny_generation
        children = []
        for name in payload.progeny_names:
            c = Material(code=next_code(db, "M"), name=name,
                         generation=gen or "F1", mating_event=event)
            db.add(c)
            children.append(c)
        db.flush()
        for c in children:
            lineage.validate_new_cross(
                db,
                cross_type=event.cross_type,
                parent_a_id=event.parent_a_id,
                parent_b_id=event.parent_b_id,
                child_id=c.id,
            )
        db.commit()
    except lineage.PedigreeError as e:
        db.rollback()
        raise HTTPException(422, str(e))

    return db.get(
        MatingEvent,
        event.id,
        options=[joinedload(MatingEvent.parent_a), joinedload(MatingEvent.parent_b)],
    )


@app.post("/api/matings/{event_id}/progeny", response_model=MaterialOut, status_code=201)
def attach_progeny(event_id: int, payload: MatingAttachProgeny, db: Session = Depends(get_db)):
    event = db.get(MatingEvent, event_id)
    if event is None:
        raise HTTPException(404, "交配事件不存在")
    child = db.get(Material, payload.material_id)
    if child is None:
        raise HTTPException(404, "材料不存在")
    try:
        lineage.validate_mating(
            db,
            cross_type=event.cross_type,
            parent_a_id=event.parent_a_id,
            parent_b_id=event.parent_b_id,
            child_ids=[c.id for c in event.progeny] + [child.id],
            exclude_event_id=event.id,
        )
        child.mating_event_id = event.id
        db.commit()
    except lineage.PedigreeError as e:
        db.rollback()
        raise HTTPException(422, str(e))
    db.refresh(child)
    return child


@app.get("/api/matings/{event_id}/mean", response_model=FamilyMeanResponse)
def family_mean(event_id: int, trait_code: str | None = None, db: Session = Depends(get_db)):
    """Simple average across progeny with real measured values for each trait.

    未测 / 死亡 rows are excluded from the mean but counted separately.
    """
    event = db.get(MatingEvent, event_id)
    if event is None:
        raise HTTPException(404, "交配事件不存在")
    progeny_ids = [c.id for c in event.progeny]

    trait_stmt = select(Trait)
    if trait_code:
        trait_stmt = trait_stmt.where(Trait.trait_code == trait_code)
    traits = db.scalars(trait_stmt.order_by(Trait.id)).all()

    items: list[FamilyMeanItem] = []
    for t in traits:
        rows = (
            db.query(Observation.status, Observation.value)
            .filter(Observation.material_id.in_(progeny_ids), Observation.trait_id == t.id)
            .all()
            if progeny_ids
            else []
        )
        n_dead = sum(1 for s, _ in rows if s == "dead")
        n_untested = sum(1 for s, _ in rows if s == "untested")
        values = [float(v) for s, v in rows if s == "measured" and v is not None]
        items.append(
            FamilyMeanItem(
                trait_code=t.trait_code,
                trait_name=t.name,
                unit=t.unit,
                n_measured=len(values),
                n_dead=n_dead,
                n_untested=n_untested,
                mean=(sum(values) / len(values)) if values else None,
            )
        )

    return FamilyMeanResponse(
        mating_event_id=event.id,
        event_code=event.event_code,
        cross_type=event.cross_type,
        items=items,
    )


# ---------------- Traits / observations ----------------

@app.get("/api/traits", response_model=list[TraitOut])
def list_traits(db: Session = Depends(get_db)):
    return db.scalars(select(Trait).order_by(Trait.id)).all()


@app.put("/api/materials/{material_id}/observations/{trait_code}",
         response_model=ObservationOut)
def upsert_observation(
    material_id: int,
    trait_code: str,
    payload: ObservationUpsert,
    db: Session = Depends(get_db),
):
    """Record or backfill an observation.

    measured requires a real numeric value; untested/dead force value NULL.
    Backfilling (未测 -> 实测) is exactly this PUT with new status/value.
    """
    m = db.get(Material, material_id)
    if m is None:
        raise HTTPException(404, "材料不存在")
    t = db.scalar(select(Trait).where(Trait.trait_code == trait_code))
    if t is None:
        raise HTTPException(404, "性状不存在")
    if payload.status == "measured" and payload.value is None:
        raise HTTPException(422, "实测记录必须提供真实数值")

    value = payload.value if payload.status == "measured" else None
    row = db.scalar(
        select(Observation).where(
            Observation.material_id == material_id, Observation.trait_id == t.id
        )
    )
    if row is None:
        row = Observation(material_id=material_id, trait_id=t.id)
        db.add(row)
    row.status = payload.status
    row.value = value
    row.observed_on = payload.observed_on
    row.source_note = payload.source_note
    db.commit()
    db.refresh(row)
    row.trait = t
    return obs_to_out(row)


# ---------------- Plots ----------------

@app.get("/api/plots", response_model=list[PlotOut])
def list_plots(db: Session = Depends(get_db)):
    plots = (
        db.query(Plot)
        .options(joinedload(Plot.material))
        .order_by(Plot.block, Plot.position)
        .all()
    )
    return [plot_to_out(p) for p in plots]


# ---------------- Static React build ----------------

STATIC_DIR = os.environ.get("STATIC_DIR", os.path.join(os.path.dirname(__file__), "..", "static"))
STATIC_DIR = os.path.abspath(STATIC_DIR)

if os.path.isdir(STATIC_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(STATIC_DIR, "assets")), name="assets")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))
