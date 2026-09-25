"""FastAPI 入口：材料、交配事件、观测、小区、谱系与家系均值。"""
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from . import models, pedigree, schemas
from .database import Base, engine, get_db

app = FastAPI(title="育种材料谱系管理（虚构数据演示）")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    Base.metadata.create_all(engine)


def make_code(material_id: int) -> str:
    return f"BM-{material_id:04d}"


def get_material_or_404(db: Session, material_id: int) -> models.Material:
    m = db.get(models.Material, material_id)
    if m is None:
        raise HTTPException(404, f"材料 #{material_id} 不存在")
    return m


def cross_out(ev: models.CrossEvent) -> schemas.CrossOut:
    return schemas.CrossOut(
        id=ev.id,
        cross_type=ev.cross_type.value,
        parent_a_id=ev.parent_a_id,
        parent_b_id=ev.parent_b_id,
        crossed_on=ev.crossed_on,
        location=ev.location,
        operator=ev.operator,
        note=ev.note,
        offspring_ids=[m.id for m in ev.offspring],
    )


# ---------- 材料 ----------

@app.post("/api/materials", response_model=schemas.MaterialOut, status_code=201)
def create_material(body: schemas.MaterialCreate, db: Session = Depends(get_db)):
    m = models.Material(name=body.name, generation=body.generation, code="tmp")
    db.add(m)
    db.flush()
    m.code = make_code(m.id)  # 稳定编号，同名材料据此区分
    db.commit()
    return m


@app.get("/api/materials", response_model=list[schemas.MaterialOut])
def list_materials(db: Session = Depends(get_db)):
    return db.query(models.Material).order_by(models.Material.id).all()


@app.get("/api/materials/{material_id}", response_model=schemas.MaterialOut)
def get_material(material_id: int, db: Session = Depends(get_db)):
    return get_material_or_404(db, material_id)


# ---------- 交配事件 ----------

@app.post("/api/crosses", response_model=schemas.CrossOut, status_code=201)
def create_cross(body: schemas.CrossCreate, db: Session = Depends(get_db)):
    for pid in {body.parent_a_id, body.parent_b_id} - {None}:
        get_material_or_404(db, pid)

    offspring_ids: list[int] = []
    if body.offspring_id is not None:
        # 关联已存在的材料（允许先登记材料、后补登记其来源交配）
        child = get_material_or_404(db, body.offspring_id)
        if child.cross_event_id is not None:
            raise HTTPException(409, f"材料 {child.code} 已有关联的交配事件")
        offspring_ids.append(child.id)
    elif body.offspring_name:
        if not body.offspring_generation:
            raise HTTPException(422, "登记后代时必须提供世代（如 F1、S1）")
        child = models.Material(
            name=body.offspring_name, generation=body.offspring_generation, code="tmp"
        )
        db.add(child)
        db.flush()
        child.code = make_code(child.id)
        offspring_ids.append(child.id)

    # NetworkX 校验：禁止材料成为自己的祖先
    try:
        pedigree.validate_new_edges(
            db, [body.parent_a_id, body.parent_b_id], offspring_ids
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(400, str(exc))

    ev = models.CrossEvent(
        cross_type=models.CrossType(body.cross_type),
        parent_a_id=body.parent_a_id,
        parent_b_id=body.parent_b_id,
        crossed_on=body.crossed_on,
        location=body.location,
        operator=body.operator,
        note=body.note,
    )
    db.add(ev)
    db.flush()
    for oid in offspring_ids:
        db.get(models.Material, oid).cross_event_id = ev.id
    db.commit()
    return cross_out(ev)


@app.get("/api/crosses", response_model=list[schemas.CrossOut])
def list_crosses(db: Session = Depends(get_db)):
    return [cross_out(ev) for ev in db.query(models.CrossEvent).order_by(models.CrossEvent.id)]


@app.post("/api/crosses/{cross_id}/offspring/{material_id}",
          response_model=schemas.CrossOut)
def attach_offspring(cross_id: int, material_id: int, db: Session = Depends(get_db)):
    """把已存在的材料挂到交配事件下（同一事件可含多份后代，构成家系）。"""
    ev = db.get(models.CrossEvent, cross_id)
    if ev is None:
        raise HTTPException(404, f"交配事件 #{cross_id} 不存在")
    child = get_material_or_404(db, material_id)
    if child.cross_event_id is not None:
        raise HTTPException(409, f"材料 {child.code} 已有关联的交配事件")
    try:
        pedigree.validate_new_edges(
            db, [ev.parent_a_id, ev.parent_b_id], [material_id]
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    child.cross_event_id = ev.id
    db.commit()
    db.refresh(ev)
    return cross_out(ev)


# ---------- 谱系回溯 ----------

@app.get("/api/materials/{material_id}/pedigree", response_model=schemas.PedigreeOut)
def get_pedigree(material_id: int, db: Session = Depends(get_db)):
    m = get_material_or_404(db, material_id)
    anc_ids = pedigree.ancestor_ids(db, material_id)

    # 计算每个祖先到该材料的世代距离（沿谱系图反向 BFS）
    g = pedigree.build_pedigree_graph(db)
    depths: dict[int, int] = {}
    if anc_ids:
        lengths = __import__("networkx").single_source_shortest_path_length(
            g.reverse(copy=False), material_id
        )
        depths = {n: d for n, d in lengths.items() if n in anc_ids}

    ancestors = []
    for aid in sorted(anc_ids, key=lambda a: depths.get(a, 0)):
        anc = db.get(models.Material, aid)
        ancestors.append(
            schemas.PedigreeNode(material=anc, depth=depths.get(aid, 0), cross_event=None)
        )

    parents = []
    if m.origin_cross:
        for p in (m.origin_cross.parent_a, m.origin_cross.parent_b):
            if p is not None and all(p.id != q.id for q in parents):
                parents.append(p)

    return schemas.PedigreeOut(
        material=m,
        parents=parents,
        cross_event=cross_out(m.origin_cross) if m.origin_cross else None,
        ancestors=ancestors,
        observations=[schemas.ObservationOut.model_validate(o) for o in m.observations],
    )


# ---------- 观测 ----------

@app.post("/api/observations", response_model=schemas.ObservationOut, status_code=201)
def create_observation(body: schemas.ObservationCreate, db: Session = Depends(get_db)):
    get_material_or_404(db, body.material_id)
    if body.plot_id is not None and db.get(models.Plot, body.plot_id) is None:
        raise HTTPException(404, f"小区 #{body.plot_id} 不存在")
    obs = models.Observation(**body.model_dump())
    db.add(obs)
    db.commit()
    return obs


@app.patch("/api/observations/{obs_id}", response_model=schemas.ObservationOut)
def patch_observation(obs_id: int, body: schemas.ObservationPatch, db: Session = Depends(get_db)):
    obs = db.get(models.Observation, obs_id)
    if obs is None:
        raise HTTPException(404, f"观测 #{obs_id} 不存在")
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(obs, k, v)
    # 补录后仍须满足 状态/数值 一致性
    if obs.status == models.ObsStatus.measured and obs.value is None:
        db.rollback()
        raise HTTPException(422, "status=measured 时必须提供数值")
    if obs.status != models.ObsStatus.measured and obs.value is not None:
        db.rollback()
        raise HTTPException(422, "未测/死亡观测不应带数值")
    db.commit()
    return obs


@app.get("/api/observations", response_model=list[schemas.ObservationOut])
def list_observations(
    material_id: int | None = None,
    trait: str | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(models.Observation)
    if material_id is not None:
        q = q.filter(models.Observation.material_id == material_id)
    if trait is not None:
        q = q.filter(models.Observation.trait == trait)
    return q.order_by(models.Observation.id).all()


@app.get("/api/traits", response_model=list[str])
def list_traits(db: Session = Depends(get_db)):
    rows = db.query(models.Observation.trait).distinct().order_by(models.Observation.trait)
    return [r[0] for r in rows]


# ---------- 家系均值 ----------

@app.get("/api/families/{cross_event_id}/mean", response_model=schemas.FamilyMeanOut)
def family_mean(
    cross_event_id: int,
    trait: str = Query(..., description="性状名，如 株高cm"),
    db: Session = Depends(get_db),
):
    ev = db.get(models.CrossEvent, cross_event_id)
    if ev is None:
        raise HTTPException(404, f"交配事件 #{cross_event_id} 不存在")
    offspring_ids = [m.id for m in ev.offspring]
    obs = (
        db.query(models.Observation)
        .filter(
            models.Observation.material_id.in_(offspring_ids or [-1]),
            models.Observation.trait == trait,
        )
        .all()
    )
    values = [o.value for o in obs if o.status == models.ObsStatus.measured]
    return schemas.FamilyMeanOut(
        cross_event_id=cross_event_id,
        trait=trait,
        mean=round(sum(values) / len(values), 3) if values else None,
        n_measured=len(values),
        n_missing=sum(1 for o in obs if o.status == models.ObsStatus.missing),
        n_dead=sum(1 for o in obs if o.status == models.ObsStatus.dead),
        offspring_count=len(offspring_ids),
    )


# ---------- 试验小区 ----------

@app.post("/api/plots", response_model=schemas.PlotOut, status_code=201)
def create_plot(body: schemas.PlotCreate, db: Session = Depends(get_db)):
    get_material_or_404(db, body.material_id)
    plot = models.Plot(**body.model_dump())
    db.add(plot)
    db.commit()
    return plot


@app.get("/api/plots")
def list_plots(db: Session = Depends(get_db)):
    plots = db.query(models.Plot).order_by(models.Plot.id).all()
    return [
        {
            "id": p.id,
            "code": p.code,
            "location": p.location,
            "replicate": p.replicate,
            "material_id": p.material_id,
            "material_code": p.material.code,
            "material_name": p.material.name,
            "generation": p.material.generation,
        }
        for p in plots
    ]
