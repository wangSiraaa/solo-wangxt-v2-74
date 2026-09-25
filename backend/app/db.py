"""Database engine / session / schema definition.

Storage: PostgreSQL.  DATABASE_URL can be overridden via environment
variable so the test-suite can point at its own database.  All data in
this project is fictional plant breeding data.
"""
from __future__ import annotations

import os

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    Sequence,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres@/breeding?host=/tmp&port=55432",
)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


# Crosses may have one or two parents; selfing uses the same material twice
# (stored once, cross_type='self').  Unknown parents stay NULL.
class Material(Base):
    __tablename__ = "materials"

    # Stable public identifier: M-0001 ... independent of the (non-unique) name.
    id: Mapped[int] = mapped_column(
        BigInteger, Sequence("materials_id_seq"), primary_key=True
    )
    code: Mapped[str] = mapped_column(String(16), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    generation: Mapped[str] = mapped_column(String(8), nullable=False)  # P / F1 / F2 ...
    species_note: Mapped[str] = mapped_column(String(128), nullable=False, default="虚构作物 Fictitious crop")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())

    mating_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("mating_events.id", ondelete="SET NULL"), nullable=True
    )
    mating_event: Mapped["MatingEvent | None"] = relationship(
        back_populates="progeny", foreign_keys=[mating_event_id]
    )


class MatingEvent(Base):
    __tablename__ = "mating_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    event_code: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)
    event_date: Mapped[Date | None] = mapped_column(Date, nullable=True)
    # self  -> only parent_a_id is set and equals the sole parent
    # cross -> two distinct parents
    # open  -> open-pollinated / unknown parents; both may be NULL
    cross_type: Mapped[str] = mapped_column(String(8), nullable=False)
    parent_a_id: Mapped[int | None] = mapped_column(
        ForeignKey("materials.id", ondelete="RESTRICT"), nullable=True
    )
    parent_b_id: Mapped[int | None] = mapped_column(
        ForeignKey("materials.id", ondelete="RESTRICT"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())

    parent_a: Mapped["Material | None"] = relationship(foreign_keys=[parent_a_id])
    parent_b: Mapped["Material | None"] = relationship(foreign_keys=[parent_b_id])
    progeny: Mapped[list["Material"]] = relationship(
        back_populates="mating_event", foreign_keys=[Material.mating_event_id]
    )

    __table_args__ = (
        CheckConstraint(
            "cross_type IN ('self','cross','open')", name="chk_mating_type"
        ),
        CheckConstraint(
            "(cross_type = 'self') = (parent_a_id IS NOT NULL AND parent_b_id IS NULL)",
            name="chk_self_parents",
        ),
        CheckConstraint(
            "cross_type <> 'cross' OR (parent_a_id IS NOT NULL AND parent_b_id IS NOT NULL)",
            name="chk_cross_parents",
        ),
        CheckConstraint(
            "cross_type <> 'cross' OR parent_a_id <> parent_b_id",
            name="chk_cross_distinct_parents",
        ),
    )


class Plot(Base):
    """试验小区: a field position where one material is observed."""

    __tablename__ = "plots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    plot_code: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)
    block: Mapped[str] = mapped_column(String(16), nullable=False)
    position: Mapped[str] = mapped_column(String(16), nullable=False)
    material_id: Mapped[int | None] = mapped_column(
        ForeignKey("materials.id", ondelete="SET NULL"), nullable=True
    )

    material: Mapped["Material | None"] = relationship()

    __table_args__ = (UniqueConstraint("block", "position", name="uq_plot_position"),)


class Trait(Base):
    __tablename__ = "traits"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    trait_code: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    unit: Mapped[str] = mapped_column(String(16), nullable=False, default="")


class Observation(Base):
    """性状观测.

    status:
      measured -> value carries the real numeric measurement
      untested -> 未测, value is NULL
      dead     -> 材料死亡, value is NULL
    Backfill is just a normal update from untested/dead to measured.
    """

    __tablename__ = "observations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    material_id: Mapped[int] = mapped_column(
        ForeignKey("materials.id", ondelete="CASCADE"), nullable=False
    )
    trait_id: Mapped[int] = mapped_column(
        ForeignKey("traits.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(8), nullable=False, default="untested")
    value: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    observed_on: Mapped[Date | None] = mapped_column(Date, nullable=True)
    recorded_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
    source_note: Mapped[str | None] = mapped_column(String(128), nullable=True)

    material: Mapped["Material"] = relationship()
    trait: Mapped["Trait"] = relationship()

    __table_args__ = (
        UniqueConstraint("material_id", "trait_id", name="uq_material_trait"),
        CheckConstraint(
            "status IN ('measured','untested','dead')", name="chk_obs_status"
        ),
        CheckConstraint(
            "(status = 'measured') = (value IS NOT NULL)",
            name="chk_measured_value",
        ),
        Index("ix_obs_trait", "trait_id"),
    )


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_schema() -> None:
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    init_schema()
    print("schema created at", DATABASE_URL)
