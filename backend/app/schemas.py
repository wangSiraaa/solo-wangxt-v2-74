"""Pydantic request/response models."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- Materials ----------

class MaterialCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    generation: str = Field("P", pattern=r"^(P|F\d+)$")
    notes: Optional[str] = None
    # Optional mating origin for the new material.
    cross_type: Optional[Literal["self", "cross", "open"]] = None
    parent_a_id: Optional[int] = None
    parent_b_id: Optional[int] = None
    event_date: Optional[date] = None


class MaterialOut(ORMModel):
    id: int
    code: str
    name: str
    generation: str
    species_note: str
    notes: Optional[str]
    mating_event_id: Optional[int]
    created_at: datetime


class ParentRef(ORMModel):
    id: int
    code: str
    name: str
    generation: str


class MatingEventOut(ORMModel):
    id: int
    event_code: str
    event_date: Optional[date]
    cross_type: str
    parent_a_id: Optional[int]
    parent_b_id: Optional[int]
    notes: Optional[str]
    parent_a: Optional[ParentRef] = None
    parent_b: Optional[ParentRef] = None


class ObservationOut(ORMModel):
    id: int
    material_id: int
    trait_id: int
    status: str
    value: Optional[float]
    observed_on: Optional[date]
    recorded_at: datetime
    source_note: Optional[str]
    trait_code: str = ""
    trait_name: str = ""
    unit: str = ""


class PlotOut(ORMModel):
    id: int
    plot_code: str
    block: str
    position: str
    material_id: Optional[int]
    material_code: Optional[str] = None
    material_name: Optional[str] = None
    generation: Optional[str] = None


class MaterialDetail(MaterialOut):
    mating_event: Optional[MatingEventOut] = None
    ancestor_ids: list[int] = []
    descendant_ids: list[int] = []
    observations: list[ObservationOut] = []
    plots: list[PlotOut] = []


# ---------- Mating events ----------

class MatingCreate(BaseModel):
    cross_type: Literal["self", "cross", "open"]
    parent_a_id: Optional[int] = None
    parent_b_id: Optional[int] = None
    event_date: Optional[date] = None
    notes: Optional[str] = None
    # New progeny registered together with the event.
    progeny_names: list[str] = Field(default_factory=list)
    progeny_generation: Optional[str] = Field(None, pattern=r"^(P|F\d+)$")


class MatingAttachProgeny(BaseModel):
    material_id: int


# ---------- Traits / observations ----------

class TraitOut(ORMModel):
    id: int
    trait_code: str
    name: str
    unit: str


class ObservationUpsert(BaseModel):
    status: Literal["measured", "untested", "dead"] = "untested"
    value: Optional[float] = None
    observed_on: Optional[date] = None
    source_note: Optional[str] = None


# ---------- Family mean ----------

class FamilyMeanItem(BaseModel):
    trait_code: str
    trait_name: str
    unit: str
    n_measured: int
    n_dead: int
    n_untested: int
    mean: Optional[float] = None


class FamilyMeanResponse(BaseModel):
    mating_event_id: int
    event_code: str
    cross_type: str
    items: list[FamilyMeanItem]
