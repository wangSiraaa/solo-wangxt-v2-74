import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "./api.js";

const STATUS_LABEL = { measured: "实测", missing: "未测", dead: "死亡" };

function MaterialTag({ m, onSelect }) {
  if (!m) return <span className="unknown">未知亲本</span>;
  return (
    <button className="tag" onClick={() => onSelect && onSelect(m.id)}>
      {m.code} · {m.name}
      <span className="gen">{m.generation}</span>
    </button>
  );
}

function MaterialList({ materials, crosses, onSelect }) {
  const crossById = useMemo(
    () => Object.fromEntries(crosses.map((c) => [c.id, c])),
    [crosses]
  );
  return (
    <table>
      <thead>
        <tr>
          <th>编号</th><th>名称</th><th>世代</th><th>来源交配</th>
        </tr>
      </thead>
      <tbody>
        {materials.map((m) => (
          <tr key={m.id} onClick={() => onSelect(m.id)} className="clickable">
            <td>{m.code}</td>
            <td>{m.name}</td>
            <td>{m.generation}</td>
            <td>
              {m.cross_event_id
                ? `#${m.cross_event_id}（${
                    crossById[m.cross_event_id]?.cross_type === "self"
                      ? "自交"
                      : "杂交"
                  }）`
                : "—（基础亲本）"}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function PedigreeView({ materialId, onSelect }) {
  const [ped, setPed] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => {
    setPed(null);
    api.pedigree(materialId).then(setPed).catch((e) => setErr(e.message));
  }, [materialId]);
  if (err) return <p className="error">{err}</p>;
  if (!ped) return <p>加载中…</p>;
  const ev = ped.cross_event;
  const byDepth = {};
  for (const n of ped.ancestors) {
    (byDepth[n.depth] = byDepth[n.depth] || []).push(n.material);
  }
  return (
    <div>
      <h3>
        谱系回溯：{ped.material.code} · {ped.material.name}（
        {ped.material.generation}）
      </h3>

      <section className="card">
        <h4>交配记录</h4>
        {ev ? (
          <div>
            <p>
              {ev.cross_type === "self" ? "自交" : "杂交"} · 日期{" "}
              {ev.crossed_on || "—"} · 地点 {ev.location || "—"} · 操作人{" "}
              {ev.operator || "—"}
            </p>
            <p>
              亲本：
              {ped.parents.length
                ? ped.parents.map((p) => (
                    <MaterialTag key={p.id} m={p} onSelect={onSelect} />
                  ))
                : "未知"}
            </p>
            {ev.note && <p className="muted">备注：{ev.note}</p>}
          </div>
        ) : (
          <p>基础亲本（P 代），无来源交配。</p>
        )}
      </section>

      <section className="card">
        <h4>祖先（按世代距离）</h4>
        {Object.keys(byDepth).length === 0 && <p>无已知祖先。</p>}
        {Object.keys(byDepth)
          .sort((a, b) => a - b)
          .map((d) => (
            <p key={d}>
              <span className="muted">上溯 {d} 代：</span>
              {byDepth[d].map((m) => (
                <MaterialTag key={m.id} m={m} onSelect={onSelect} />
              ))}
            </p>
          ))}
      </section>

      <section className="card">
        <h4>观测记录（含来源）</h4>
        {ped.observations.length === 0 ? (
          <p>暂无观测。</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>性状</th><th>数值/状态</th><th>来源</th><th>日期</th><th>备注</th>
              </tr>
            </thead>
            <tbody>
              {ped.observations.map((o) => (
                <tr key={o.id}>
                  <td>{o.trait}</td>
                  <td>
                    {o.status === "measured" ? (
                      o.value
                    ) : (
                      <span className={`status-${o.status}`}>
                        {STATUS_LABEL[o.status]}
                      </span>
                    )}
                  </td>
                  <td>{o.source}</td>
                  <td>{o.observed_on || "—"}</td>
                  <td>{o.note || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}

function PlotsView({ plots, onSelect }) {
  return (
    <table>
      <thead>
        <tr>
          <th>小区</th><th>地点</th><th>重复</th><th>种植材料</th><th>世代</th>
        </tr>
      </thead>
      <tbody>
        {plots.map((p) => (
          <tr key={p.id} onClick={() => onSelect(p.material_id)} className="clickable">
            <td>{p.code}</td>
            <td>{p.location}</td>
            <td>{p.replicate}</td>
            <td>
              {p.material_code} · {p.material_name}
            </td>
            <td>{p.generation}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function FamilyMean({ crosses, materials, traits }) {
  const [crossId, setCrossId] = useState("");
  const [trait, setTrait] = useState("");
  const [result, setResult] = useState(null);
  const matById = useMemo(
    () => Object.fromEntries(materials.map((m) => [m.id, m])),
    [materials]
  );
  useEffect(() => {
    setResult(null);
    if (crossId && trait)
      api.familyMean(crossId, trait).then(setResult).catch(() => {});
  }, [crossId, trait]);
  const label = (c) => {
    const p = (id) => (id ? `${matById[id]?.code}·${matById[id]?.name}` : "未知");
    return `#${c.id} ${c.cross_type === "self" ? "自交" : "杂交"}：${p(
      c.parent_a_id
    )} × ${p(c.parent_b_id)}（后代 ${c.offspring_ids.length} 份）`;
  };
  return (
    <div>
      <div className="form-row">
        <label>家系（交配事件）</label>
        <select value={crossId} onChange={(e) => setCrossId(e.target.value)}>
          <option value="">请选择</option>
          {crosses.map((c) => (
            <option key={c.id} value={c.id}>
              {label(c)}
            </option>
          ))}
        </select>
        <label>性状</label>
        <select value={trait} onChange={(e) => setTrait(e.target.value)}>
          <option value="">请选择</option>
          {traits.map((t) => (
            <option key={t}>{t}</option>
          ))}
        </select>
      </div>
      {result && (
        <section className="card">
          <h4>家系均值：{result.trait}</h4>
          <p className="mean">
            {result.mean === null ? "无有效实测值" : result.mean}
          </p>
          <p className="muted">
            家系后代 {result.offspring_count} 份；计入均值 {result.n_measured}{" "}
            条实测，未测 {result.n_missing} 条、死亡 {result.n_dead}{" "}
            条（均不参与平均）
          </p>
        </section>
      )}
    </div>
  );
}

function Register({ materials, traits, missingObs, onDone }) {
  const [msg, setMsg] = useState(null);
  const [cross, setCross] = useState({
    cross_type: "cross",
    parent_a_id: "",
    parent_b_id: "",
    offspring_name: "",
    offspring_generation: "",
    operator: "",
    location: "",
  });
  const [obs, setObs] = useState({
    material_id: "",
    trait: "",
    status: "measured",
    value: "",
    source: "",
  });
  const [backfill, setBackfill] = useState({ id: "", value: "", source: "" });

  const run = (fn, okText) => async (e) => {
    e.preventDefault();
    setMsg(null);
    try {
      await fn();
      setMsg({ ok: true, text: okText });
      onDone();
    } catch (err) {
      setMsg({ ok: false, text: err.message });
    }
  };

  const parentOptions = (
    <>
      <option value="">未知</option>
      {materials.map((m) => (
        <option key={m.id} value={m.id}>
          {m.code} · {m.name}（{m.generation}）
        </option>
      ))}
    </>
  );

  return (
    <div>
      {msg && (
        <p className={msg.ok ? "ok" : "error"}>{msg.text}</p>
      )}
      <section className="card">
        <h4>登记交配（自交 / 杂交）</h4>
        <form
          onSubmit={run(async () => {
            const body = {
              cross_type: cross.cross_type,
              parent_a_id: cross.parent_a_id ? Number(cross.parent_a_id) : null,
              parent_b_id:
                cross.cross_type === "self"
                  ? undefined
                  : cross.parent_b_id
                  ? Number(cross.parent_b_id)
                  : null,
              operator: cross.operator || null,
              location: cross.location || null,
            };
            if (cross.offspring_name) {
              body.offspring_name = cross.offspring_name;
              body.offspring_generation = cross.offspring_generation;
            }
            await api.createCross(body);
          }, "交配事件已登记")}
        >
          <div className="form-row">
            <select
              value={cross.cross_type}
              onChange={(e) => setCross({ ...cross, cross_type: e.target.value })}
            >
              <option value="cross">杂交（双亲）</option>
              <option value="self">自交</option>
            </select>
            <label>亲本A</label>
            <select
              value={cross.parent_a_id}
              onChange={(e) => setCross({ ...cross, parent_a_id: e.target.value })}
            >
              {parentOptions}
            </select>
            {cross.cross_type === "cross" && (
              <>
                <label>亲本B</label>
                <select
                  value={cross.parent_b_id}
                  onChange={(e) =>
                    setCross({ ...cross, parent_b_id: e.target.value })
                  }
                >
                  {parentOptions}
                </select>
              </>
            )}
          </div>
          <div className="form-row">
            <label>后代名称</label>
            <input
              value={cross.offspring_name}
              onChange={(e) =>
                setCross({ ...cross, offspring_name: e.target.value })
              }
              placeholder="可留空，仅登记交配"
            />
            <label>世代</label>
            <input
              value={cross.offspring_generation}
              onChange={(e) =>
                setCross({ ...cross, offspring_generation: e.target.value })
              }
              placeholder="如 F1 / S1"
              style={{ width: "7em" }}
            />
            <label>操作人</label>
            <input
              value={cross.operator}
              onChange={(e) => setCross({ ...cross, operator: e.target.value })}
              style={{ width: "8em" }}
            />
            <button type="submit">登记</button>
          </div>
        </form>
      </section>

      <section className="card">
        <h4>登记观测</h4>
        <form
          onSubmit={run(async () => {
            await api.createObservation({
              material_id: Number(obs.material_id),
              trait: obs.trait,
              status: obs.status,
              value: obs.status === "measured" ? Number(obs.value) : null,
              source: obs.source,
            });
          }, "观测已登记")}
        >
          <div className="form-row">
            <label>材料</label>
            <select
              value={obs.material_id}
              onChange={(e) => setObs({ ...obs, material_id: e.target.value })}
            >
              <option value="">请选择</option>
              {materials.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.code} · {m.name}
                </option>
              ))}
            </select>
            <label>性状</label>
            <input
              list="traits"
              value={obs.trait}
              onChange={(e) => setObs({ ...obs, trait: e.target.value })}
            />
            <datalist id="traits">
              {traits.map((t) => (
                <option key={t} value={t} />
              ))}
            </datalist>
            <select
              value={obs.status}
              onChange={(e) => setObs({ ...obs, status: e.target.value })}
            >
              <option value="measured">实测</option>
              <option value="missing">未测</option>
              <option value="dead">死亡</option>
            </select>
            {obs.status === "measured" && (
              <input
                type="number"
                step="any"
                placeholder="数值"
                value={obs.value}
                onChange={(e) => setObs({ ...obs, value: e.target.value })}
                style={{ width: "7em" }}
              />
            )}
            <input
              placeholder="来源（记录人/批次）"
              value={obs.source}
              onChange={(e) => setObs({ ...obs, source: e.target.value })}
            />
            <button type="submit">登记</button>
          </div>
        </form>
      </section>

      <section className="card">
        <h4>观测补录（未测 → 实测）</h4>
        {missingObs.length === 0 ? (
          <p className="muted">当前没有未测观测。</p>
        ) : (
          <form
            onSubmit={run(async () => {
              await api.patchObservation(Number(backfill.id), {
                status: "measured",
                value: Number(backfill.value),
                source: backfill.source || undefined,
              });
              setBackfill({ id: "", value: "", source: "" });
            }, "补录完成")}
          >
            <div className="form-row">
              <select
                value={backfill.id}
                onChange={(e) => setBackfill({ ...backfill, id: e.target.value })}
              >
                <option value="">选择未测观测</option>
                {missingObs.map((o) => (
                  <option key={o.id} value={o.id}>
                    #{o.id} 材料{o.material_id} · {o.trait}
                  </option>
                ))}
              </select>
              <input
                type="number"
                step="any"
                placeholder="补录数值"
                value={backfill.value}
                onChange={(e) =>
                  setBackfill({ ...backfill, value: e.target.value })
                }
                style={{ width: "8em" }}
              />
              <input
                placeholder="补录来源"
                value={backfill.source}
                onChange={(e) =>
                  setBackfill({ ...backfill, source: e.target.value })
                }
              />
              <button type="submit">补录</button>
            </div>
          </form>
        )}
      </section>
    </div>
  );
}

export default function App() {
  const [tab, setTab] = useState("materials");
  const [materials, setMaterials] = useState([]);
  const [crosses, setCrosses] = useState([]);
  const [plots, setPlots] = useState([]);
  const [traits, setTraits] = useState([]);
  const [missingObs, setMissingObs] = useState([]);
  const [selected, setSelected] = useState(null);

  const refresh = useCallback(async () => {
    const [m, c, p, t, o] = await Promise.all([
      api.materials(),
      api.crosses(),
      api.plots(),
      api.traits(),
      api.observations(),
    ]);
    setMaterials(m);
    setCrosses(c);
    setPlots(p);
    setTraits(t);
    setMissingObs(o.filter((x) => x.status === "missing"));
  }, []);

  useEffect(() => {
    refresh().catch(console.error);
  }, [refresh]);

  const selectMaterial = (id) => {
    setSelected(id);
    setTab("pedigree");
  };

  return (
    <div className="app">
      <h1>育种材料谱系管理 <span className="badge">虚构数据演示</span></h1>
      <nav>
        {[
          ["materials", "材料列表"],
          ["pedigree", "谱系回溯"],
          ["plots", "试验小区"],
          ["family", "家系均值"],
          ["register", "登记"],
        ].map(([k, label]) => (
          <button
            key={k}
            className={tab === k ? "active" : ""}
            onClick={() => setTab(k)}
            disabled={k === "pedigree" && selected === null}
          >
            {label}
          </button>
        ))}
      </nav>
      <main>
        {tab === "materials" && (
          <MaterialList materials={materials} crosses={crosses} onSelect={selectMaterial} />
        )}
        {tab === "pedigree" && selected !== null && (
          <PedigreeView materialId={selected} onSelect={selectMaterial} />
        )}
        {tab === "plots" && <PlotsView plots={plots} onSelect={selectMaterial} />}
        {tab === "family" && (
          <FamilyMean crosses={crosses} materials={materials} traits={traits} />
        )}
        {tab === "register" && (
          <Register
            materials={materials}
            traits={traits}
            missingObs={missingObs}
            onDone={refresh}
          />
        )}
      </main>
    </div>
  );
}
