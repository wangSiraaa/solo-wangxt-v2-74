"""End-to-end verification on a throwaway PostgreSQL database.

Creates database ``breeding_test``, seeds the two-generation fictional
dataset, and verifies:

1. materials are stable-code distinguished, including same-name materials;
2. selecting a progeny traces back parents + mating record + observation source;
3. a material can never become its own ancestor (NetworkX rejection);
4. unknown parents stay empty;
5. observations distinguish untested / dead / measured;
6. backfill flips untested -> measured with a recorded source;
7. family simple mean counts only real measured values.

Run from backend/:  python -m tests.test_api
"""
from __future__ import annotations

import os
import sys

import psycopg2

TEST_DB = "breeding_test"
DSN_ADMIN = "host=/tmp port=55432 user=postgres dbname=postgres"
os.environ["DATABASE_URL"] = (
    f"postgresql+psycopg2://postgres@/{TEST_DB}?host=/tmp&port=55432"
)

# (re)create a clean test database
conn = psycopg2.connect(DSN_ADMIN)
conn.autocommit = True
with conn.cursor() as cur:
    cur.execute(f"DROP DATABASE IF EXISTS {TEST_DB}")
    cur.execute(f"CREATE DATABASE {TEST_DB}")
conn.close()

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app import seed as seed_module  # noqa: E402

seed_module.seed()
client = TestClient(app)

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {label}" + (f" -- {detail}" if detail else ""))
    if not ok:
        failures.append(label)


# 1. health
r = client.get("/api/health")
check("health ok", r.status_code == 200 and r.json()["storage"] == "postgresql")

# 2. materials list + stable codes + same names
mats = client.get("/api/materials").json()
check("8 materials seeded", len(mats) == 8, f"got {len(mats)}")
codes = [m["code"] for m in mats]
check("stable codes unique", len(set(codes)) == len(codes))
same_name = [m for m in mats if m["name"] == "晨露"]
check("same-name 晨露 distinguished by code",
      {m["code"] for m in same_name} == {"M-0001", "M-0003"},
      str([(m["code"], m["generation"]) for m in same_name]))
f1_same = [m for m in mats if m["name"] == "晨星1号"]
check("same-name F1 progeny distinguished", len(f1_same) == 3
      and len({m["code"] for m in f1_same}) == 3)

by_code = {m["code"]: m for m in mats}

# 3. select a progeny -> trace parents, mating event, observation source
detail = client.get("/api/materials/M-0004").json()  # actually path id=4
# IDs are numeric: find F1 晨星1号 first child
f1a = by_code["M-0004"]
detail = client.get(f"/api/materials/{f1a['id']}").json()
ev = detail["mating_event"]
check("progeny linked to mating event", ev is not None and ev["cross_type"] == "cross")
parent_codes = {ev["parent_a"]["code"], ev["parent_b"]["code"]}
check("parents traceable 晨露 M-0001 x 星穗 M-0002",
      parent_codes == {"M-0001", "M-0002"}, str(parent_codes))
check("ancestor ids = both parents",
      set(detail["ancestor_ids"]) == {ev["parent_a_id"], ev["parent_b_id"]},
      str(detail["ancestor_ids"]))
plh = next(o for o in detail["observations"] if o["trait_code"] == "PLH")
check("measured observation carries value + source",
      plh["status"] == "measured" and plh["value"] == 88.0
      and "F1 鉴定圃" in (plh["source_note"] or ""),
      str(plh))

# selfing progeny
f1d = by_code["M-0007"]
d7 = client.get(f"/api/materials/{f1d['id']}").json()
sev = d7["mating_event"]
check("selfing event has one parent M-0003",
      sev["cross_type"] == "self" and sev["parent_a"]["code"] == "M-0003"
      and sev["parent_b"] is None)

# 4. unknown parents stay empty
f1e = by_code["M-0008"]
d8 = client.get(f"/api/materials/{f1e['id']}").json()
oev = d8["mating_event"]
check("open event keeps unknown parents empty",
      oev["cross_type"] == "open" and oev["parent_a"] is None and oev["parent_b"] is None)

# 5. observation states untested/dead/measured
d5 = client.get(f"/api/materials/{by_code['M-0005']['id']}").json()
yld_b = next(o for o in d5["observations"] if o["trait_code"] == "YLD")
check("dead observation has no value", yld_b["status"] == "dead" and yld_b["value"] is None)
d6 = client.get(f"/api/materials/{by_code['M-0006']['id']}").json()
plh_c = next(o for o in d6["observations"] if o["trait_code"] == "PLH")
check("untested observation has no value",
      plh_c["status"] == "untested" and plh_c["value"] is None)
d8obs = {o["trait_code"]: o for o in d8["observations"]}
check("dead/untested both represented",
      d8obs["PLH"]["status"] == "dead" and d8obs["YLD"]["status"] == "untested")

# measured without value must be rejected
bad = client.put(f"/api/materials/{f1a['id']}/observations/SUG",
                 json={"status": "measured", "value": None})
check("measured requires numeric value", bad.status_code == 422)

# 6. backfill: M-0007 PLH already backfilled by seed
plh7 = next(o for o in d7["observations"] if o["trait_code"] == "PLH")
check("seed backfill untested->measured with source",
      plh7["status"] == "measured" and plh7["value"] == 80.5
      and "补录" in (plh7["source_note"] or ""), str(plh7))

# backfill via API: M-0006 PLH untested -> measured
r = client.put(f"/api/materials/{by_code['M-0006']['id']}/observations/PLH",
               json={"status": "measured", "value": 90.0,
                     "source_note": "API 补录：田间补测表 R-2026-011"})
check("API backfill returns measured value",
      r.status_code == 200 and r.json()["value"] == 90.0
      and "补录" in r.json()["source_note"], str(r.status_code))

# 7. family mean for cross family X-0001
cross_id = ev["id"]
mean = client.get(f"/api/matings/{cross_id}/mean").json()
by_trait = {i["trait_code"]: i for i in mean["items"]}
plh_mean = by_trait["PLH"]
# PLH: 88, 91, untested -> after API backfill M-0006 becomes 90 -> n=3, mean=89.6667
check("PLH simple mean over measured only",
      plh_mean["n_measured"] == 3 and plh_mean["n_untested"] == 0
      and abs(plh_mean["mean"] - (88.0 + 91.0 + 90.0) / 3) < 1e-6,
      str(plh_mean))
yld_mean = by_trait["YLD"]
# YLD: 198, dead, 176 -> n=2 mean=187
check("YLD excludes dead, mean=187",
      yld_mean["n_measured"] == 2 and yld_mean["n_dead"] == 1
      and abs(yld_mean["mean"] - 187.0) < 1e-6, str(yld_mean))

# selected trait filter
one = client.get(f"/api/matings/{cross_id}/mean?trait_code=YLD").json()
check("trait filter returns one item", len(one["items"]) == 1
      and one["items"][0]["trait_code"] == "YLD")

# selfing family mean X-0002
self_mean = client.get(f"/api/matings/{sev['id']}/mean").json()
sm = {i["trait_code"]: i for i in self_mean["items"]}
check("selfing family PLH mean 80.5",
      sm["PLH"]["n_measured"] == 1 and sm["PLH"]["mean"] == 80.5)

# 8. self-ancestor / cycle rejection
# create plain material, then try a mating with itself as both parents
newm = client.post("/api/materials", json={"name": "悖论苗", "generation": "F1"}).json()
r = client.post("/api/matings", json={
    "cross_type": "cross",
    "parent_a_id": newm["id"], "parent_b_id": newm["id"],
    "progeny_names": ["不该出现"],
})
check("identical-parents cross rejected", r.status_code == 422, r.text[:200])

# self-ancestor via attachment: new event parented by M-0004 (a descendant
# of M-0001), then attach M-0001 as progeny -> M-0001 -> M-0004 -> M-0001
rev = client.post("/api/matings", json={
    "cross_type": "self", "parent_a_id": by_code["M-0004"]["id"],
    "notes": "构造用：子代作为亲本的反向事件",
}).json()
r = client.post(f"/api/matings/{rev['id']}/progeny",
                json={"material_id": by_code["M-0001"]["id"]})
check("material-as-own-ancestor rejected (cycle)",
      r.status_code == 422 and "祖先" in r.json()["detail"], r.text[:200])

# selfing requiring a parent
r = client.post("/api/matings", json={"cross_type": "self", "progeny_names": ["x"]})
check("selfing without parent rejected", r.status_code == 422)

# cross with missing second parent
r = client.post("/api/matings", json={
    "cross_type": "cross", "parent_a_id": by_code["M-0001"]["id"],
    "progeny_names": ["x"],
})
check("cross with one parent rejected", r.status_code == 422)

# 9. plots
plots = client.get("/api/plots").json()
check("8 plots with materials", len(plots) == 8
      and all(p["material_code"] for p in plots), f"{len(plots)} plots")
b2 = [p for p in plots if p["block"] == "B2"]
check("B2 plots hold F1 family", len(b2) == 3
      and {p["generation"] for p in b2} == {"F1"})

print()
if failures:
    print(f"{len(failures)} CHECK(S) FAILED: {failures}")
    sys.exit(1)
print("ALL CHECKS PASSED")
