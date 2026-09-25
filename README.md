# 虚构作物育种管理系统（亲本组合 · 世代 · 家系田间观测）

全栈示例：**React**（材料列表 / 谱系 / 试验小区）+ **FastAPI**（NetworkX 关系图校验）
+ **PostgreSQL**（材料身份、交配事件、性状观测）。全部数据为**虚构植物数据**，
不包含、也不执行任何生物实验操作。

## 数据模型（PostgreSQL）

| 表 | 说明 |
|---|---|
| `materials` | 材料身份：`M-xxxx` 稳定编号（唯一）、名称（可重复）、世代 P/F1/F2…、来源交配事件 |
| `mating_events` | 交配事件：`self` 自交（1 个亲本）/ `cross` 杂交（2 个不同亲本）/ `open` 亲本未知（留空） |
| `observations` | 性状观测，状态三态互斥：`measured` 实测（必须有数值）/ `untested` 未测 / `dead` 死亡（数值为空） |
| `traits` | 性状字典：株高 PLH、单株果重 YLD、糖度 SUG、开花天数 DAY |
| `plots` | 试验小区：区组 + 位置 + 定植材料 |

关键约束：
- 同名材料允许共存，靠 `M-xxxx` 稳定编号区分（如两个“晨露”、三个“晨星1号”）。
- 未知亲本显式保持为 `NULL`（`open` 事件）。
- `CHECK` 约束：杂交必须双亲齐全且不同；实测行必须有数值；未测/死亡行数值为空。

## NetworkX 谱系校验

`backend/app/lineage.py` 从交配事件构建 `parent → child` 有向图（自交不产生祖先边）：

- `nx.is_directed_acyclic_graph` / `nx.find_cycle`：登记/挂载后代时禁止成环——
  **材料永远不能成为自己的祖先**；
- `nx.ancestors` / `nx.descendants`：选中一个后代即可回溯全部亲本与交配记录；
- 登记前先在应用层校验亲本存在、类型与双亲互异，再写库。

## 家系简单平均值

`GET /api/matings/{id}/mean?trait_code=`：以交配事件的全部后代为家系，
**只对 `measured` 实测值求简单平均**；未测、死亡分别计数但不进入均值。

## 虚构验证数据集（两代）

- P 代：`M-0001 晨露`、`M-0002 星穗`、`M-0003 晨露`（与 M-0001 同名的不同材料）
- 杂交 `X-0001`：晨露(M-0001) × 星穗(M-0002) → 三个同名 F1：
  `M-0004/M-0005/M-0006 晨星1号`
- 自交 `X-0002`：晨露(M-0003) 自交 → `M-0007 晨露自交1代`（株高由“未测”**补录**为 80.5）
- 开放授粉 `X-0003`：亲本留空 → `M-0008 野采苗`（定植后死亡）
- 观测三态：M-0004 株高 88 cm 实测（来源“F1 鉴定圃”）；M-0005 果重**死亡**；
  M-0006 株高**未测**（可在界面补录）

## 运行方式

```bash
# 1) PostgreSQL（示例为本机用户态实例，端口 55432，socket /tmp）
#    建库：createdb -p 55432 -h /tmp -U postgres breeding
# 2) 后端
cd backend
pip install -r requirements.txt
python -m app.seed                      # 建表并写入虚构数据（可重复执行）
python -m uvicorn app.main:app --port 8000
# 3) 前端（开发）
cd frontend && npm install && npm run dev      # http://localhost:5173
#    或构建到 backend/static，由 FastAPI 直接托管：npm run build
```

连接串可用 `DATABASE_URL` 覆盖，默认：
`postgresql+psycopg2://postgres@/breeding?host=/tmp&port=55432`

## 验证（自动化，30 项全部通过）

```bash
cd backend && python -m tests.test_api
```

覆盖：稳定编号/同名区分、后代→亲本/交配记录/观测来源回溯、
成环与同亲本杂交拒绝（422）、未知亲本留空、未测/死亡/实测三态、
观测补录、家系简单平均（死亡/未测不入均值）、试验小区布局。

验证示例（在线接口实测）：

```
POST /matings/{反向事件}/progeny {"material_id": 1}
→ 422 {"detail":"禁止材料成为自己的祖先: 检测到关系环 1 -> 4"}
GET  /matings/1/mean        → PLH mean=89.5（88,91；第3株未测）
PUT  /materials/6/observations/PLH {measured, 90.0, 补测表 R-2026-011}
GET  /matings/1/mean?PLH    → mean=89.6667，实测数 3
```
