"""写入虚构演示数据：P / F1 / F2 三代（两代交配）、同名材料、未知亲本、
观测（含未测、死亡、补录）。全部为虚构植物数据，仅用于系统演示。

运行：python -m app.seed
"""
from datetime import date

from .database import Base, SessionLocal, engine
from .main import make_code
from .models import CrossEvent, CrossType, Material, Observation, ObsStatus, Plot


def add_material(db, name, generation, cross_event_id=None) -> Material:
    m = Material(name=name, generation=generation, code="tmp",
                 cross_event_id=cross_event_id)
    db.add(m)
    db.flush()
    m.code = make_code(m.id)
    return m


def add_cross(db, ctype, pa, pb, on, loc, op, note=None) -> CrossEvent:
    ev = CrossEvent(cross_type=ctype, parent_a_id=pa, parent_b_id=pb,
                    crossed_on=on, location=loc, operator=op, note=note)
    db.add(ev)
    db.flush()
    return ev


def add_obs(db, material_id, trait, status, value, source, on, plot_id=None, note=None):
    obs = Observation(material_id=material_id, plot_id=plot_id, trait=trait,
                      status=status, value=value, source=source,
                      observed_on=on, note=note)
    db.add(obs)
    db.flush()
    return obs


def main():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = SessionLocal()

    # ---- P 代（基础亲本，含同名材料 “金穗”）----
    jinsui_a = add_material(db, "金穗", "P")      # BM-0001
    jinsui_b = add_material(db, "金穗", "P")      # BM-0002（同名，靠编号区分）
    yulu = add_material(db, "玉露", "P")          # BM-0003

    # ---- 第一次交配（产生 F1 / S1）----
    ev1 = add_cross(db, CrossType.cross, jinsui_a.id, yulu.id,
                    date(2024, 4, 10), "晨曦试验站-1号棚", "记录员-岚",
                    "金穗(BM-0001) × 玉露")
    chenxi1 = add_material(db, "晨曦1号", "F1", ev1.id)          # BM-0004

    ev2 = add_cross(db, CrossType.self_, jinsui_b.id, jinsui_b.id,
                    date(2024, 4, 12), "晨曦试验站-1号棚", "记录员-岚",
                    "金穗(BM-0002) 自交")
    jinsui_s1 = add_material(db, "金穗S1", "S1", ev2.id)         # BM-0005

    # 一个亲本未知的杂交：晨曦1号 × 未知
    ev3 = add_cross(db, CrossType.cross, chenxi1.id, None,
                    date(2024, 4, 20), "晨曦试验站-2号棚", "记录员-苔",
                    "花粉亲本未知（开放授粉）")
    chenxi2 = add_material(db, "晨曦2号", "F1", ev3.id)          # BM-0006

    # ---- 第二次交配（产生 F2，共两代材料繁衍）----
    ev4 = add_cross(db, CrossType.self_, chenxi1.id, chenxi1.id,
                    date(2025, 4, 8), "晨曦试验站-1号棚", "记录员-岚",
                    "晨曦1号 自交")
    f2_a = add_material(db, "晨曦1号F2-甲", "F2", ev4.id)        # BM-0007
    f2_b = add_material(db, "晨曦1号F2-乙", "F2", ev4.id)        # BM-0008

    ev5 = add_cross(db, CrossType.cross, chenxi1.id, jinsui_s1.id,
                    date(2025, 4, 9), "晨曦试验站-1号棚", "记录员-苔",
                    "晨曦1号 × 金穗S1")
    f2_c = add_material(db, "晨曦3号", "F2", ev5.id)             # BM-0009

    # ---- 试验小区 ----
    plots = [
        Plot(code="A-101", location="晨曦试验站-东区", replicate=1, material_id=jinsui_a.id),
        Plot(code="A-102", location="晨曦试验站-东区", replicate=1, material_id=jinsui_b.id),
        Plot(code="A-103", location="晨曦试验站-东区", replicate=1, material_id=yulu.id),
        Plot(code="B-201", location="晨曦试验站-西区", replicate=1, material_id=chenxi1.id),
        Plot(code="B-202", location="晨曦试验站-西区", replicate=1, material_id=jinsui_s1.id),
        Plot(code="C-301", location="晨曦试验站-北区", replicate=1, material_id=f2_a.id),
        Plot(code="C-302", location="晨曦试验站-北区", replicate=1, material_id=f2_b.id),
        Plot(code="C-303", location="晨曦试验站-北区", replicate=1, material_id=f2_c.id),
    ]
    db.add_all(plots)
    db.flush()
    plot_by_code = {p.code: p.id for p in plots}

    # ---- 观测：区分 实测 / 未测 / 死亡；含一条“先未测、后补录” ----
    d = date(2025, 7, 15)
    # P 代
    add_obs(db, jinsui_a.id, "株高cm", ObsStatus.measured, 92.5, "观测员-禾", d, plot_by_code["A-101"])
    add_obs(db, jinsui_b.id, "株高cm", ObsStatus.measured, 88.0, "观测员-禾", d, plot_by_code["A-102"])
    add_obs(db, yulu.id, "株高cm", ObsStatus.measured, 105.3, "观测员-禾", d, plot_by_code["A-103"])
    # F1
    add_obs(db, chenxi1.id, "株高cm", ObsStatus.measured, 98.4, "观测员-禾", d, plot_by_code["B-201"])
    add_obs(db, jinsui_s1.id, "株高cm", ObsStatus.measured, 84.1, "观测员-禾", d, plot_by_code["B-202"])
    add_obs(db, chenxi2.id, "株高cm", ObsStatus.missing, None, "观测员-禾", d, note="当季未安排测量")
    # F2（家系 ev4 的两个后代 + ev5 的一个后代）
    add_obs(db, f2_a.id, "株高cm", ObsStatus.measured, 95.0, "观测员-禾", d, plot_by_code["C-301"])
    add_obs(db, f2_b.id, "株高cm", ObsStatus.dead, None, "观测员-禾", d, plot_by_code["C-302"], note="苗期枯死，非数值 0")
    add_obs(db, f2_c.id, "株高cm", ObsStatus.measured, 90.2, "观测员-禾", d, plot_by_code["C-303"])

    # 穗粒数：f2_a 先登记为未测，之后补录真实数值（演示观测补录）
    backfill = add_obs(db, f2_a.id, "穗粒数", ObsStatus.missing, None, "观测员-禾", d,
                       plot_by_code["C-301"], note="脱粒后补测")
    add_obs(db, f2_b.id, "穗粒数", ObsStatus.dead, None, "观测员-禾", d, plot_by_code["C-302"])
    add_obs(db, f2_c.id, "穗粒数", ObsStatus.measured, 41.0, "观测员-禾", d, plot_by_code["C-303"])

    # 补录：未测 -> 实测
    backfill.status = ObsStatus.measured
    backfill.value = 38.0
    backfill.source = "观测员-禾（补录）"
    backfill.note = "2025-07-20 脱粒后补测"

    db.commit()

    print("演示数据已写入：")
    for m in db.query(Material).order_by(Material.id):
        print(f"  {m.code}  {m.name:<12} 世代={m.generation}  来源交配={m.cross_event_id}")
    print(f"交配事件 {db.query(CrossEvent).count()} 条，观测 {db.query(Observation).count()} 条，"
          f"小区 {db.query(Plot).count()} 个")
    db.close()


if __name__ == "__main__":
    main()
