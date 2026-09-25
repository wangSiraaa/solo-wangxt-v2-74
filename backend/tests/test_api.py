"""测试使用独立的 breeding_test 数据库（PostgreSQL），每个用例前清空表。"""
import os

os.environ["DATABASE_URL"] = "postgresql+psycopg2://node@localhost:5432/breeding_test"

import psycopg2
import pytest
from fastapi.testclient import TestClient

from app.database import Base, engine, get_db
from app.main import app


def ensure_test_db():
    conn = psycopg2.connect(dbname="postgres", user="node", host="localhost", port=5432)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM pg_database WHERE datname='breeding_test'")
    if cur.fetchone() is None:
        cur.execute("CREATE DATABASE breeding_test")
    conn.close()


ensure_test_db()


@pytest.fixture()
def client():
    # materials 与 cross_events 互为外键，drop_all 无法排序，直接重建 schema
    with engine.begin() as conn:
        conn.exec_driver_sql("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    Base.metadata.create_all(engine)
    with TestClient(app) as c:
        yield c


def mk_material(client, name, gen):
    r = client.post("/api/materials", json={"name": name, "generation": gen})
    assert r.status_code == 201, r.text
    return r.json()


def test_same_name_materials_get_distinct_stable_codes(client):
    a = mk_material(client, "金穗", "P")
    b = mk_material(client, "金穗", "P")
    assert a["name"] == b["name"] == "金穗"
    assert a["code"] != b["code"]
    # 编号稳定：再次查询不变
    again = client.get(f"/api/materials/{a['id']}").json()
    assert again["code"] == a["code"]


def test_self_cross_and_unknown_parent(client):
    p = mk_material(client, "金穗", "P")
    # 自交
    r = client.post("/api/crosses", json={
        "cross_type": "self", "parent_a_id": p["id"],
        "offspring_name": "金穗S1", "offspring_generation": "S1",
    })
    assert r.status_code == 201, r.text
    ev = r.json()
    assert ev["parent_a_id"] == ev["parent_b_id"] == p["id"]
    # 一个亲本未知的杂交
    r = client.post("/api/crosses", json={
        "cross_type": "cross", "parent_a_id": p["id"], "parent_b_id": None,
        "offspring_name": "晨曦X", "offspring_generation": "F1",
    })
    assert r.status_code == 201, r.text
    assert r.json()["parent_b_id"] is None
    # 双亲都未知则拒绝
    r = client.post("/api/crosses", json={"cross_type": "cross"})
    assert r.status_code == 422


def test_material_cannot_become_its_own_ancestor(client):
    # 甲 -> 乙（先建材料乙，再补登记来源交配）
    a = mk_material(client, "甲", "P")
    b = mk_material(client, "乙", "F1")
    r = client.post("/api/crosses", json={
        "cross_type": "self", "parent_a_id": a["id"], "offspring_id": b["id"],
    })
    assert r.status_code == 201, r.text
    # 乙 -> 丙
    c = mk_material(client, "丙", "F2")
    r = client.post("/api/crosses", json={
        "cross_type": "self", "parent_a_id": b["id"], "offspring_id": c["id"],
    })
    assert r.status_code == 201, r.text
    # 禁止（跨代环）：丙 作为亲本产生 甲 —— 甲已是丙的祖先
    r = client.post("/api/crosses", json={
        "cross_type": "cross", "parent_a_id": c["id"], "parent_b_id": b["id"],
        "offspring_id": a["id"],
    })
    assert r.status_code == 400
    assert "祖先" in r.json()["detail"]
    # 禁止（直接环）：乙 作为亲本产生 甲
    r = client.post("/api/crosses", json={
        "cross_type": "self", "parent_a_id": b["id"], "offspring_id": a["id"],
    })
    assert r.status_code == 400
    # 禁止：材料作为自己的亲本
    r = client.post("/api/crosses", json={
        "cross_type": "self", "parent_a_id": a["id"], "offspring_id": a["id"],
    })
    assert r.status_code == 400
    # 合法关系不受影响：丙 -> 丁
    d = mk_material(client, "丁", "F3")
    r = client.post("/api/crosses", json={
        "cross_type": "self", "parent_a_id": c["id"], "offspring_id": d["id"],
    })
    assert r.status_code == 201


def test_observation_status_rules(client):
    m = mk_material(client, "观测材料", "F1")
    # measured 必须有数值
    r = client.post("/api/observations", json={
        "material_id": m["id"], "trait": "株高cm", "status": "measured", "source": "观测员-禾",
    })
    assert r.status_code == 422
    # missing/dead 不能带数值
    r = client.post("/api/observations", json={
        "material_id": m["id"], "trait": "株高cm", "status": "dead",
        "value": 10.0, "source": "观测员-禾",
    })
    assert r.status_code == 422
    # 合法：死亡（无数值）
    r = client.post("/api/observations", json={
        "material_id": m["id"], "trait": "株高cm", "status": "dead", "source": "观测员-禾",
    })
    assert r.status_code == 201
    assert r.json()["value"] is None


def test_observation_backfill_and_family_mean(client):
    # 家系：亲本 P 自交，同一交配事件下三份 F2 后代
    p = mk_material(client, "亲本", "P")
    r = client.post("/api/crosses", json={
        "cross_type": "self", "parent_a_id": p["id"],
        "offspring_name": "F2-1", "offspring_generation": "F2",
    })
    ev_id = r.json()["id"]
    kid1 = r.json()["offspring_ids"][0]
    kid2 = mk_material(client, "F2-2", "F2")
    kid3 = mk_material(client, "F2-3", "F2")
    for kid in (kid2, kid3):
        r = client.post(f"/api/crosses/{ev_id}/offspring/{kid['id']}")
        assert r.status_code == 200, r.text
    assert sorted(r.json()["offspring_ids"]) == sorted([kid1, kid2["id"], kid3["id"]])

    # kid1: 实测 90；kid2: 实测 100；kid3: 死亡（无数值）
    client.post("/api/observations", json={
        "material_id": kid1, "trait": "株高cm", "status": "measured",
        "value": 90.0, "source": "观测员-禾",
    })
    client.post("/api/observations", json={
        "material_id": kid2["id"], "trait": "株高cm", "status": "measured",
        "value": 100.0, "source": "观测员-禾",
    })
    client.post("/api/observations", json={
        "material_id": kid3["id"], "trait": "株高cm", "status": "dead",
        "source": "观测员-禾",
    })
    # kid1 另有一条未测的穗粒数
    r = client.post("/api/observations", json={
        "material_id": kid1, "trait": "穗粒数", "status": "missing", "source": "观测员-禾",
    })
    obs_id = r.json()["id"]

    # 株高家系均值 = (90+100)/2 = 95，死亡不计入
    mean = client.get(f"/api/families/{ev_id}/mean", params={"trait": "株高cm"}).json()
    assert mean["mean"] == 95.0
    assert mean["n_measured"] == 2 and mean["n_dead"] == 1
    assert mean["offspring_count"] == 3
    # 穗粒数：仅一条未测 -> 无均值
    mean = client.get(f"/api/families/{ev_id}/mean", params={"trait": "穗粒数"}).json()
    assert mean["mean"] is None and mean["n_missing"] == 1
    # 补录：未测 -> 实测 38，均值随之出现
    r = client.patch(f"/api/observations/{obs_id}", json={
        "status": "measured", "value": 38.0, "source": "观测员-禾（补录）",
    })
    assert r.status_code == 200, r.text
    mean = client.get(f"/api/families/{ev_id}/mean", params={"trait": "穗粒数"}).json()
    assert mean["mean"] == 38.0 and mean["n_measured"] == 1 and mean["n_missing"] == 0
    # 补录非法：改回 missing 但数值还在
    r = client.patch(f"/api/observations/{obs_id}", json={"status": "missing"})
    assert r.status_code == 422


def test_pedigree_trace_from_descendant(client):
    """选择后代可回溯：亲本、交配记录、观测来源。"""
    p1 = mk_material(client, "金穗", "P")
    p2 = mk_material(client, "玉露", "P")
    r = client.post("/api/crosses", json={
        "cross_type": "cross", "parent_a_id": p1["id"], "parent_b_id": p2["id"],
        "crossed_on": "2024-04-10", "location": "晨曦试验站", "operator": "记录员-岚",
        "offspring_name": "晨曦1号", "offspring_generation": "F1",
    })
    f1 = r.json()["offspring_ids"][0]
    r = client.post("/api/crosses", json={
        "cross_type": "self", "parent_a_id": f1,
        "offspring_name": "晨曦1号F2", "offspring_generation": "F2",
    })
    f2 = r.json()["offspring_ids"][0]
    client.post("/api/observations", json={
        "material_id": f2, "trait": "株高cm", "status": "measured",
        "value": 95.0, "source": "观测员-禾",
    })

    ped = client.get(f"/api/materials/{f2}/pedigree").json()
    # 直接亲本 = 晨曦1号
    assert [p["name"] for p in ped["parents"]] == ["晨曦1号"]
    # 产生该材料的交配记录
    assert ped["cross_event"]["cross_type"] == "self"
    assert ped["cross_event"]["parent_a_id"] == f1
    # 祖先包含 F1 与两个 P 代
    anc_names = {n["material"]["name"] for n in ped["ancestors"]}
    assert anc_names == {"晨曦1号", "金穗", "玉露"}
    depths = {n["material"]["name"]: n["depth"] for n in ped["ancestors"]}
    assert depths["晨曦1号"] == 1 and depths["金穗"] == 2 and depths["玉露"] == 2
    # 观测来源可溯
    assert ped["observations"][0]["source"] == "观测员-禾"
    assert ped["observations"][0]["value"] == 95.0
