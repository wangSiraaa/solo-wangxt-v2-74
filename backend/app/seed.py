"""Idempotent seed of FICTIONAL plant data: two generations, same-name
materials, three observation states, and one backfilled observation.

Run:  python -m app.seed
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import text

from .db import Base, Material, MatingEvent, Observation, Plot, SessionLocal, Trait, engine

MAT_NO = 0
EV_NO = 0
PLOT_NO = 0


def mat_code() -> str:
    global MAT_NO
    MAT_NO += 1
    return f"M-{MAT_NO:04d}"


def ev_code() -> str:
    global EV_NO
    EV_NO += 1
    return f"X-{EV_NO:04d}"


def plot_code() -> str:
    global PLOT_NO
    PLOT_NO += 1
    return f"P-{PLOT_NO:04d}"


def reset() -> None:
    # materials <-> mating_events form a deliberate FK cycle, so recreate
    # the schema with raw DROP ... CASCADE instead of metadata.drop_all.
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS observations CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS plots CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS materials CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS mating_events CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS traits CASCADE"))
        conn.execute(text("DROP SEQUENCE IF EXISTS materials_id_seq CASCADE"))
    Base.metadata.create_all(bind=engine)


def seed() -> None:
    reset()
    db = SessionLocal()
    try:
        # ----- traits -----
        traits = {
            "PLH": Trait(trait_code="PLH", name="株高", unit="cm"),
            "YLD": Trait(trait_code="YLD", name="单株果重", unit="g"),
            "SUG": Trait(trait_code="SUG", name="糖度", unit="°Brix"),
            "DAY": Trait(trait_code="DAY", name="开花天数", unit="d"),
        }
        db.add_all(traits.values())
        db.flush()

        # ----- generation P (founders) -----
        p1 = Material(code=mat_code(), name="晨露", generation="P",
                      notes="虚构高糖亲本")
        p2 = Material(code=mat_code(), name="星穗", generation="P",
                      notes="虚构丰产亲本")
        p3 = Material(code=mat_code(), name="晨露", generation="P",
                      notes="与 M-0001 同名的不同材料（稳定编号区分）")
        for m in (p1, p2, p3):
            db.add(m)
        db.flush()

        # ----- mating events (registered BEFORE progeny for FK ordering) -----
        cross = MatingEvent(
            event_code=ev_code(), event_date=date(2026, 3, 10),
            cross_type="cross", parent_a_id=p1.id, parent_b_id=p2.id,
            notes="虚构杂交组合: 晨露(M-0001) × 星穗(M-0002)",
        )
        selfing = MatingEvent(
            event_code=ev_code(), event_date=date(2026, 3, 12),
            cross_type="self", parent_a_id=p3.id,
            notes="虚构自交: 晨露(M-0003) 自交",
        )
        db.add_all([cross, selfing])
        db.flush()

        # ----- generation F1 progeny -----
        f1_a = Material(code=mat_code(), name="晨星1号", generation="F1",
                        mating_event_id=cross.id, notes="家系 X-0001 单株 A")
        f1_b = Material(code=mat_code(), name="晨星1号", generation="F1",
                        mating_event_id=cross.id, notes="家系 X-0001 单株 B（同名材料）")
        f1_c = Material(code=mat_code(), name="晨星1号", generation="F1",
                        mating_event_id=cross.id, notes="家系 X-0001 单株 C（同名材料）")
        f1_d = Material(code=mat_code(), name="晨露自交1代", generation="F1",
                        mating_event_id=selfing.id,
                        notes="家系 X-0002；性状经观测补录")
        # unknown-parent material (open pollination event, both parents empty)
        open_ev = MatingEvent(
            event_code=ev_code(), event_date=date(2026, 3, 15),
            cross_type="open", parent_a_id=None, parent_b_id=None,
            notes="虚构开放授粉材料，亲本未知保持为空",
        )
        db.add(open_ev)
        db.add_all([f1_a, f1_b, f1_c, f1_d])
        db.flush()
        f1_e = Material(code=mat_code(), name="野采苗", generation="F1",
                        mating_event_id=open_ev.id, notes="亲本未知")
        db.add(f1_e)
        db.flush()

        # ----- plots 试验小区 -----
        plots = [
            Plot(plot_code=plot_code(), block="B1", position="01", material_id=p1.id),
            Plot(plot_code=plot_code(), block="B1", position="02", material_id=p2.id),
            Plot(plot_code=plot_code(), block="B1", position="03", material_id=p3.id),
            Plot(plot_code=plot_code(), block="B2", position="01", material_id=f1_a.id),
            Plot(plot_code=plot_code(), block="B2", position="02", material_id=f1_b.id),
            Plot(plot_code=plot_code(), block="B2", position="03", material_id=f1_c.id),
            Plot(plot_code=plot_code(), block="B3", position="01", material_id=f1_d.id),
            Plot(plot_code=plot_code(), block="B3", position="02", material_id=f1_e.id),
        ]
        db.add_all(plots)

        # ----- observations: measured / untested / dead -----
        def obs(material, code, status, value=None, on=None, note=None):
            return Observation(
                material_id=material.id, trait_id=traits[code].id,
                status=status, value=value, observed_on=on, source_note=note,
            )

        # founder measurements
        db.add_all([
            obs(p1, "PLH", "measured", 82.0, date(2026, 5, 2), "亲本圃"),
            obs(p1, "SUG", "measured", 12.5, date(2026, 6, 1), "亲本圃"),
            obs(p2, "PLH", "measured", 95.0, date(2026, 5, 2), "亲本圃"),
            obs(p2, "YLD", "measured", 210.0, date(2026, 6, 5), "亲本圃"),
            obs(p3, "PLH", "measured", 78.0, date(2026, 5, 2), "亲本圃"),
        ])

        # F1 family X-0001: real values, one death, one untested (later backfilled? no)
        db.add_all([
            obs(f1_a, "PLH", "measured", 88.0, date(2026, 5, 20), "F1 鉴定圃"),
            obs(f1_a, "YLD", "measured", 198.0, date(2026, 6, 10), "F1 鉴定圃"),
            obs(f1_b, "PLH", "measured", 91.0, date(2026, 5, 20), "F1 鉴定圃"),
            obs(f1_b, "YLD", "dead", None, None, "花期涝害死亡"),
            obs(f1_c, "PLH", "untested", None, None, "未测：等待下一轮观测"),
            obs(f1_c, "YLD", "measured", 176.0, date(2026, 6, 10), "F1 鉴定圃"),
        ])

        # F1 family X-0002 (selfing): PLH first untested, then backfilled.
        db.add_all([
            obs(f1_d, "PLH", "untested", None, None, "初登记：未测"),
            obs(f1_d, "SUG", "measured", 11.2, date(2026, 6, 2), "F1 鉴定圃"),
        ])

        # open-pollinated plant: dead before measurement
        db.add_all([
            obs(f1_e, "PLH", "dead", None, None, "定植后萎蔫死亡"),
            obs(f1_e, "YLD", "untested", None, None, "未测"),
        ])

        db.commit()

        # ----- backfill demonstration: M-0007 PLH untested -> measured -----
        backfilled = obs(
            f1_d, "PLH", "measured", 80.5, date(2026, 6, 8),
            "观测补录：由未测更新为实测（补录来源：田间补测表 R-2026-009）",
        )
        # replace the existing untested row via direct update
        row = (
            db.query(Observation)
            .filter_by(material_id=f1_d.id, trait_id=traits["PLH"].id)
            .one()
        )
        row.status = backfilled.status
        row.value = backfilled.value
        row.observed_on = backfilled.observed_on
        row.source_note = backfilled.source_note
        db.commit()

        print("seed complete: 8 materials, 3 mating events, 4 traits, 8 plots, 14 observations")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
