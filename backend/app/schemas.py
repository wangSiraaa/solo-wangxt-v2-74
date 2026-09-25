"""Pydantic 请求/响应模型。"""
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class MaterialCreate(BaseModel):
    name: str
    generation: str


class MaterialOut(BaseModel):
    id: int
    code: str
    name: str
    generation: str
    cross_event_id: int | None

    class Config:
        from_attributes = True


class CrossCreate(BaseModel):
    cross_type: Literal["self", "cross"]
    parent_a_id: int | None = None
    parent_b_id: int | None = None
    crossed_on: date | None = None
    location: str | None = None
    operator: str | None = None
    note: str | None = None
    # 可选：同时登记后代 —— 新建（名称+世代）或关联已存在的材料
    offspring_name: str | None = None
    offspring_generation: str | None = None
    offspring_id: int | None = None

    @model_validator(mode="after")
    def check_parents(self):
        if self.cross_type == "self":
            if self.parent_a_id is None:
                raise ValueError("自交必须提供亲本 parent_a_id")
            # 自交时两个亲本视为同一个体
            self.parent_b_id = self.parent_a_id
        else:
            if self.parent_a_id is None and self.parent_b_id is None:
                raise ValueError("杂交至少需要一个已知亲本（未知亲本可留空其一）")
            if (
                self.parent_a_id is not None
                and self.parent_a_id == self.parent_b_id
            ):
                raise ValueError("双亲亲本相同请使用自交（self）")
        return self


class CrossOut(BaseModel):
    id: int
    cross_type: str
    parent_a_id: int | None
    parent_b_id: int | None
    crossed_on: date | None
    location: str | None
    operator: str | None
    note: str | None
    offspring_ids: list[int] = []

    class Config:
        from_attributes = True


class ObservationCreate(BaseModel):
    material_id: int
    plot_id: int | None = None
    trait: str
    status: Literal["measured", "missing", "dead"] = "measured"
    value: float | None = None
    source: str
    observed_on: date | None = None
    note: str | None = None

    @model_validator(mode="after")
    def check_value(self):
        if self.status == "measured" and self.value is None:
            raise ValueError("status=measured 时必须提供数值")
        if self.status in ("missing", "dead") and self.value is not None:
            raise ValueError("未测/死亡观测不应带数值")
        return self


class ObservationPatch(BaseModel):
    """观测补录：把未测记录补上数值，或修正状态。"""

    status: Literal["measured", "missing", "dead"] | None = None
    value: float | None = None
    source: str | None = None
    note: str | None = None


class ObservationOut(BaseModel):
    id: int
    material_id: int
    plot_id: int | None
    trait: str
    value: float | None
    status: str
    source: str
    observed_on: date | None
    note: str | None

    class Config:
        from_attributes = True


class PlotCreate(BaseModel):
    code: str
    location: str
    replicate: int = 1
    material_id: int


class PlotOut(BaseModel):
    id: int
    code: str
    location: str
    replicate: int
    material_id: int

    class Config:
        from_attributes = True


class FamilyMeanOut(BaseModel):
    cross_event_id: int
    trait: str
    mean: float | None
    n_measured: int
    n_missing: int
    n_dead: int
    offspring_count: int


class PedigreeNode(BaseModel):
    material: MaterialOut
    depth: int  # 与选中材料的世代距离（1=亲本）
    cross_event: CrossOut | None  # 由哪次交配产生该祖先的下一代链条中可见


class PedigreeOut(BaseModel):
    material: MaterialOut
    parents: list[MaterialOut] = []
    cross_event: CrossOut | None  # 产生该材料的交配记录
    ancestors: list[PedigreeNode] = []
    observations: list[ObservationOut] = []
