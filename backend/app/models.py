"""SQLAlchemy 模型：材料身份、交配事件、性状观测、试验小区。"""
import enum
from datetime import date, datetime

from sqlalchemy import (CheckConstraint, Date, DateTime, Enum, Float, ForeignKey,
                        Integer, String, Text, func)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class CrossType(str, enum.Enum):
    self_ = "self"    # 自交
    cross = "cross"   # 两个亲本的杂交


class ObsStatus(str, enum.Enum):
    measured = "measured"  # 真实数值
    missing = "missing"    # 未测
    dead = "dead"          # 死亡（植株缺失，非数值 0）


class Material(Base):
    """育种材料。code 为稳定编号（同名材料靠它区分），name 可重复。"""

    __tablename__ = "materials"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100), index=True)
    generation: Mapped[str] = mapped_column(String(10))  # P / F1 / F2 / S1 ...
    # 产生该材料的交配事件；基础亲本（P 代）为空
    cross_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("cross_events.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    origin_cross: Mapped["CrossEvent | None"] = relationship(
        "CrossEvent", foreign_keys=[cross_event_id], back_populates="offspring"
    )
    observations: Mapped[list["Observation"]] = relationship(
        back_populates="material", cascade="all, delete-orphan"
    )
    plots: Mapped[list["Plot"]] = relationship(back_populates="material")


class CrossEvent(Base):
    """交配事件：自交（parent_a == parent_b）或双亲亲本杂交；未知亲本为 NULL。"""

    __tablename__ = "cross_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    cross_type: Mapped[CrossType] = mapped_column(Enum(CrossType), nullable=False)
    parent_a_id: Mapped[int | None] = mapped_column(
        ForeignKey("materials.id"), nullable=True
    )
    parent_b_id: Mapped[int | None] = mapped_column(
        ForeignKey("materials.id"), nullable=True
    )
    crossed_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    location: Mapped[str | None] = mapped_column(String(100), nullable=True)
    operator: Mapped[str | None] = mapped_column(String(50), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    parent_a: Mapped[Material | None] = relationship(foreign_keys=[parent_a_id])
    parent_b: Mapped[Material | None] = relationship(foreign_keys=[parent_b_id])
    offspring: Mapped[list[Material]] = relationship(
        "Material", foreign_keys=[Material.cross_event_id], back_populates="origin_cross"
    )


class Observation(Base):
    """性状观测。status=measured 时 value 必填；missing/dead 时 value 必须为 NULL。"""

    __tablename__ = "observations"
    __table_args__ = (
        CheckConstraint(
            "(status = 'measured' AND value IS NOT NULL) OR "
            "(status IN ('missing', 'dead') AND value IS NULL)",
            name="ck_observation_status_value",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id"), index=True)
    plot_id: Mapped[int | None] = mapped_column(ForeignKey("plots.id"), nullable=True)
    trait: Mapped[str] = mapped_column(String(50), index=True)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[ObsStatus] = mapped_column(
        Enum(ObsStatus), nullable=False, default=ObsStatus.measured
    )
    source: Mapped[str] = mapped_column(String(100))  # 观测来源：记录人/批次
    observed_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    material: Mapped[Material] = relationship(back_populates="observations")
    plot: Mapped["Plot | None"] = relationship(back_populates="observations")


class Plot(Base):
    """试验小区：田间种植单元，关联一份材料。"""

    __tablename__ = "plots"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)  # 如 A-101
    location: Mapped[str] = mapped_column(String(100))
    replicate: Mapped[int] = mapped_column(Integer, default=1)
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id"))

    material: Mapped[Material] = relationship(back_populates="plots")
    observations: Mapped[list[Observation]] = relationship(back_populates="plot")
