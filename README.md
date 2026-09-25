# 育种材料谱系管理系统（虚构数据演示）

管理亲本组合、世代与家系田间观测的全栈演示。**所有植物数据均为虚构，不涉及任何生物实验操作。**

- **React**（`frontend/`）：材料列表、谱系回溯、试验小区、家系均值、登记表单
- **FastAPI + NetworkX**（`backend/`）：以有向图校验谱系关系，禁止材料成为自己的祖先
- **PostgreSQL**：材料身份、交配事件、性状观测、试验小区

## 领域规则

| 规则 | 实现 |
|---|---|
| 自交 / 双亲杂交 | `CrossEvent.cross_type`，自交时 parent_a == parent_b |
| 禁止成为自己的祖先 | `pedigree.py` 用 NetworkX 建 亲本→后代 有向图，新增边前检查是否成环（400） |
| 同名材料区分 | 稳定编号 `BM-0001`…（由主键生成，永不复用），名称可重复 |
| 未知亲本 | `parent_a_id` / `parent_b_id` 允许 NULL，图上不产生边 |
| 未测 / 死亡 / 实测 | `Observation.status` + CHECK 约束：实测必有值，未测/死亡必无值 |
| 观测补录 | `PATCH /api/observations/{id}`，补录后仍校验状态/数值一致 |
| 家系均值 | 同一交配事件的全部后代，仅对实测值做简单算术平均 |

## 目录

```
backend/
  app/
    database.py   # 连接（DATABASE_URL 可覆盖）
    models.py     # Material / CrossEvent / Observation / Plot
    pedigree.py   # NetworkX 图校验与祖先回溯
    schemas.py    # Pydantic 模型
    main.py       # REST API
    seed.py       # 虚构演示数据（P/F1/F2、同名材料、未知亲本、补录）
  tests/test_api.py
frontend/         # Vite + React
```

## 运行

```bash
# 1. PostgreSQL（本仓库 .pgsql/ 为免安装二进制；亦可用任意本机实例）
.pgsql/extracted/bin/pg_ctl -D .pgsql/data -l .pgsql/pg.log -o "-p 5432 -k /tmp" start

# 2. 后端（写入演示数据并启动）
cd backend
python3 -m app.seed
python3 -m uvicorn app.main:app --port 8000

# 3. 前端
cd frontend && npm install && npx vite   # http://localhost:5173

# 测试（使用独立的 breeding_test 数据库）
cd backend && python3 -m pytest tests/ -q
```

## 主要 API

- `POST /api/materials` 登记材料（自动生成稳定编号）
- `POST /api/crosses` 登记交配（可同时新建或关联后代；NetworkX 环校验）
- `POST /api/crosses/{id}/offspring/{material_id}` 把已有材料挂入家系
- `GET /api/materials/{id}/pedigree` 回溯亲本、交配记录、祖先链、观测来源
- `POST /api/observations` / `PATCH /api/observations/{id}` 观测与补录
- `GET /api/families/{cross_id}/mean?trait=…` 家系简单平均值
- `GET /api/plots` 试验小区

## 演示数据验证点

- 同名材料：`金穗` 同时是 BM-0001 与 BM-0002
- 两代材料：P → F1/S1 → F2（BM-0009 晨曦3号 可回溯到 BM-0004×BM-0005 及全部 P 代祖先）
- 未知亲本：交配 #3（BM-0006 晨曦2号，花粉亲本未知）
- 观测补录：BM-0007 穗粒数先登记“未测”，后补录为 38.0（来源“观测员-禾（补录）”）
- 家系均值：交配 #4 家系株高均值只计实测，死亡个体（BM-0008）不参与
