import { useEffect, useMemo, useState } from 'react'
import { api } from './api'

const STATUS_LABEL = { measured: '实测', untested: '未测', dead: '死亡' }

function useApi(loader, deps = []) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const reload = () => {
    setLoading(true)
    loader()
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }
  useEffect(reload, deps)
  return { data, error, loading, reload, setData }
}

export default function App() {
  const [tab, setTab] = useState('materials')
  const [selectedId, setSelectedId] = useState(null)
  const [health, setHealth] = useState('')

  useEffect(() => {
    api.health().then((h) => setHealth(`${h.status} / ${h.storage}`)).catch(() => setHealth('后端不可用'))
  }, [])

  const openMaterial = (id) => {
    setSelectedId(id)
    setTab('detail')
  }

  return (
    <div className="app">
      <header>
        <h1>🌱 虚构作物育种管理系统</h1>
        <span className="health">API: {health} · 数据均为虚构植物数据，无生物实验</span>
      </header>
      <nav>
        {[
          ['materials', '材料列表'],
          ['pedigree', '谱系与交配'],
          ['plots', '试验小区'],
          ...(selectedId ? [['detail', `材料详情`]] : []),
        ].map(([k, label]) => (
          <button key={k} className={tab === k ? 'active' : ''} onClick={() => setTab(k)}>
            {label}
          </button>
        ))}
      </nav>
      <main>
        {tab === 'materials' && <MaterialsTab onSelect={openMaterial} />}
        {tab === 'pedigree' && <PedigreeTab onSelect={openMaterial} />}
        {tab === 'plots' && <PlotsTab onSelect={openMaterial} />}
        {tab === 'detail' && selectedId && (
          <DetailTab id={selectedId} onSelect={openMaterial} />
        )}
      </main>
    </div>
  )
}

/* ---------------- 材料列表 ---------------- */

function MaterialsTab({ onSelect }) {
  const [q, setQ] = useState('')
  const { data: materials, loading, error, reload } = useApi(
    () => api.materials(q),
    [q],
  )
  const { data: traits } = useApi(() => api.traits(), [])

  return (
    <section>
      <div className="toolbar">
        <input placeholder="按名称搜索，例如：晨露" value={q} onChange={(e) => setQ(e.target.value)} />
        <button onClick={reload}>刷新</button>
        <CreateMaterialForm traits={traits} onCreated={reload} />
      </div>
      {error && <p className="error">{error}</p>}
      {loading && <p>加载中…</p>}
      <table>
        <thead>
          <tr><th>稳定编号</th><th>名称</th><th>世代</th><th>备注</th><th></th></tr>
        </thead>
        <tbody>
          {(materials || []).map((m) => (
            <tr key={m.id}>
              <td className="code">{m.code}</td>
              <td>{m.name}</td>
              <td><span className="gen">{m.generation}</span></td>
              <td className="muted">{m.notes}</td>
              <td><button onClick={() => onSelect(m.id)}>查看谱系/观测</button></td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="hint">同名材料（如两个“晨露”、三个“晨星1号”）依靠 M-xxxx 稳定编号区分。</p>
    </section>
  )
}

function CreateMaterialForm({ onCreated }) {
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({ name: '', generation: 'P', notes: '' })
  const [error, setError] = useState('')
  const submit = async (e) => {
    e.preventDefault()
    setError('')
    try {
      await api.createMaterial(form)
      setOpen(false)
      setForm({ name: '', generation: 'P', notes: '' })
      onCreated()
    } catch (err) {
      setError(err.message)
    }
  }
  if (!open) return <button onClick={() => setOpen(true)}>＋ 登记新材料</button>
  return (
    <form className="inline-form" onSubmit={submit}>
      <input required placeholder="名称" value={form.name}
             onChange={(e) => setForm({ ...form, name: e.target.value })} />
      <select value={form.generation}
              onChange={(e) => setForm({ ...form, generation: e.target.value })}>
        <option>P</option><option>F1</option><option>F2</option>
      </select>
      <input placeholder="备注（可选）" value={form.notes}
             onChange={(e) => setForm({ ...form, notes: e.target.value })} />
      <button type="submit">保存</button>
      <button type="button" onClick={() => setOpen(false)}>取消</button>
      {error && <span className="error">{error}</span>}
    </form>
  )
}

/* ---------------- 谱系与交配 / 家系均值 ---------------- */

function PedigreeTab({ onSelect }) {
  const { data: materials } = useApi(() => api.materials(), [])
  const { data: matings, error, loading, reload } = useApi(() => api.matings(), [])
  const [meanEventId, setMeanEventId] = useState(null)
  const [traitFilter, setTraitFilter] = useState('')
  const { data: mean } = useApi(
    () => (meanEventId ? api.familyMean(meanEventId, traitFilter) : Promise.resolve(null)),
    [meanEventId, traitFilter],
  )

  const matById = useMemo(
    () => Object.fromEntries((materials || []).map((m) => [m.id, m])),
    [materials],
  )

  return (
    <section>
      <h2>交配事件（亲本组合 → 后代家系）</h2>
      {error && <p className="error">{error}</p>}
      {loading && <p>加载中…</p>}
      <div className="cards">
        {(matings || []).map((ev) => (
          <div key={ev.id} className={`card type-${ev.cross_type}`}>
            <div className="card-head">
              <strong>{ev.event_code}</strong>
              <span className="tag">{ev.cross_type === 'self' ? '自交' : ev.cross_type === 'cross' ? '杂交' : '开放/未知'}</span>
            </div>
            <div className="cross-row">
              {ev.parent_a ? (
                <ParentChip m={ev.parent_a} onSelect={onSelect} />
              ) : (
                <span className="unknown">亲本未知（空）</span>
              )}
              {ev.cross_type === 'cross' && (
                <>
                  <span className="cross-symbol">×</span>
                  {ev.parent_b ? <ParentChip m={ev.parent_b} onSelect={onSelect} /> : <span className="unknown">亲本未知（空）</span>}
                </>
              )}
              {ev.cross_type === 'self' && <span className="cross-symbol">⊗ 自交</span>}
            </div>
            <p className="muted small">{ev.notes}</p>
            <ProgenyList eventId={ev.id} onSelect={onSelect} />
            <button onClick={() => { setMeanEventId(ev.id); setTraitFilter('') }}>
              计算家系简单平均值
            </button>
            {mean && meanEventId === ev.id && <FamilyMean mean={mean} traitFilter={traitFilter} setTraitFilter={setTraitFilter} />}
          </div>
        ))}
      </div>
      <CreateMatingForm materials={materials || []} onCreated={reload} />
    </section>
  )
}

function ParentChip({ m, onSelect }) {
  return (
    <button className="chip" title={m.code} onClick={() => onSelect(m.id)}>
      <span className="code">{m.code}</span> {m.name} <span className="gen">{m.generation}</span>
    </button>
  )
}

function ProgenyList({ eventId, onSelect }) {
  const { data: materials } = useApi(() => api.materials(), [])
  const kids = (materials || []).filter((m) => m.mating_event_id === eventId)
  if (!kids.length) return <p className="muted small">暂无登记后代</p>
  return (
    <div className="progeny">
      <span className="small muted">后代家系：</span>
      {kids.map((k) => (
        <button key={k.id} className="chip kid" onClick={() => onSelect(k.id)}>
          <span className="code">{k.code}</span> {k.name}
        </button>
      ))}
    </div>
  )
}

function FamilyMean({ mean, traitFilter, setTraitFilter }) {
  return (
    <div className="mean">
      <select value={traitFilter} onChange={(e) => setTraitFilter(e.target.value)}>
        <option value="">全部性状</option>
        {mean.items.map((i) => <option key={i.trait_code} value={i.trait_code}>{i.trait_name}</option>)}
      </select>
      <table>
        <thead><tr><th>性状</th><th>实测数</th><th>死亡</th><th>未测</th><th>简单平均</th></tr></thead>
        <tbody>
          {mean.items.map((i) => (
            <tr key={i.trait_code}>
              <td>{i.trait_name} ({i.unit})</td>
              <td>{i.n_measured}</td>
              <td>{i.n_dead}</td>
              <td>{i.n_untested}</td>
              <td><strong>{i.mean === null ? '—' : i.mean.toFixed(2)}</strong></td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="hint">平均仅统计真实实测值；未测与死亡参与计数但不进入均值。</p>
    </div>
  )
}

function CreateMatingForm({ materials, onCreated }) {
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({
    cross_type: 'cross', parent_a_id: '', parent_b_id: '',
    progeny_names: '', progeny_generation: 'F1', notes: '',
  })
  const [error, setError] = useState('')

  const submit = async (e) => {
    e.preventDefault()
    setError('')
    const body = {
      cross_type: form.cross_type,
      parent_a_id: form.parent_a_id ? Number(form.parent_a_id) : null,
      parent_b_id: form.cross_type === 'cross' && form.parent_b_id ? Number(form.parent_b_id) : null,
      progeny_generation: form.progeny_generation,
      progeny_names: form.progeny_names.split(/[，,\s]+/).filter(Boolean),
      notes: form.notes || null,
    }
    try {
      await api.createMating(body)
      setOpen(false)
      onCreated()
    } catch (err) {
      setError(err.message)
    }
  }

  if (!open) return <button className="big-add" onClick={() => setOpen(true)}>＋ 登记自交 / 杂交组合</button>
  return (
    <form className="panel-form" onSubmit={submit}>
      <h3>新交配事件</h3>
      <label>类型
        <select value={form.cross_type} onChange={(e) => setForm({ ...form, cross_type: e.target.value })}>
          <option value="cross">杂交（两个亲本）</option>
          <option value="self">自交（一个亲本）</option>
          <option value="open">开放授粉（亲本未知，留空）</option>
        </select>
      </label>
      <label>亲本 A
        <select value={form.parent_a_id} disabled={form.cross_type === 'open'}
                onChange={(e) => setForm({ ...form, parent_a_id: e.target.value })}>
          <option value="">{form.cross_type === 'open' ? '空（未知）' : '请选择'}</option>
          {materials.map((m) => <option key={m.id} value={m.id}>{m.code} {m.name} ({m.generation})</option>)}
        </select>
      </label>
      {form.cross_type === 'cross' && (
        <label>亲本 B
          <select value={form.parent_b_id}
                  onChange={(e) => setForm({ ...form, parent_b_id: e.target.value })}>
            <option value="">请选择（须与 A 不同）</option>
            {materials.map((m) => <option key={m.id} value={m.id}>{m.code} {m.name} ({m.generation})</option>)}
          </select>
        </label>
      )}
      <label>后代名称（逗号或空格分隔，同名可用相同名称）
        <input value={form.progeny_names} placeholder="晨星1号, 晨星1号"
               onChange={(e) => setForm({ ...form, progeny_names: e.target.value })} />
      </label>
      <label>后代世代
        <select value={form.progeny_generation}
                onChange={(e) => setForm({ ...form, progeny_generation: e.target.value })}>
          <option>F1</option><option>F2</option><option>P</option>
        </select>
      </label>
      <label>备注 <input value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></label>
      <div className="row">
        <button type="submit">保存并校验谱系</button>
        <button type="button" onClick={() => setOpen(false)}>取消</button>
      </div>
      {error && <p className="error">校验失败：{error}</p>}
    </form>
  )
}

/* ---------------- 试验小区 ---------------- */

function PlotsTab({ onSelect }) {
  const { data: plots, loading, error } = useApi(() => api.plots(), [])
  const byBlock = useMemo(() => {
    const map = {}
    for (const p of plots || []) {
      (map[p.block] ||= []).push(p)
    }
    return map
  }, [plots])

  return (
    <section>
      <h2>试验小区布局</h2>
      {error && <p className="error">{error}</p>}
      {loading && <p>加载中…</p>}
      {Object.entries(byBlock).map(([block, ps]) => (
        <div key={block} className="block-row">
          <h3>区组 {block}</h3>
          <div className="plots">
            {ps.map((p) => (
              <button key={p.id} className="plot" onClick={() => p.material_id && onSelect(p.material_id)}>
                <span className="plot-code">{p.plot_code}</span>
                <span>{p.material_code} {p.material_name}</span>
                <span className="gen">{p.generation}</span>
                <span className="muted small">位置 {p.position}</span>
              </button>
            ))}
          </div>
        </div>
      ))}
    </section>
  )
}

/* ---------------- 材料详情：回溯亲本、交配记录、观测来源 ---------------- */

function DetailTab({ id, onSelect }) {
  const { data: m, error, loading, reload } = useApi(() => api.material(id), [id])
  const { data: materials } = useApi(() => api.materials(), [])
  const matById = useMemo(
    () => Object.fromEntries((materials || []).map((x) => [x.id, x])),
    [materials],
  )

  if (loading) return <p>加载中…</p>
  if (error) return <p className="error">{error}</p>
  if (!m) return null
  const ev = m.mating_event

  return (
    <section>
      <button onClick={() => history.back()} className="back">← 返回</button>
      <h2><span className="code">{m.code}</span> {m.name} <span className="gen">{m.generation}</span></h2>
      <p className="muted">{m.notes} · {m.species_note}</p>

      <div className="detail-grid">
        <div className="panel">
          <h3>亲本 / 交配记录回溯</h3>
          {ev ? (
            <>
              <p>来自交配事件 <strong>{ev.event_code}</strong>
                （{ev.cross_type === 'self' ? '自交' : ev.cross_type === 'cross' ? '两亲本杂交' : '开放授粉'}）
                {ev.event_date ? ` · ${ev.event_date}` : ''}
              </p>
              <div className="cross-row">
                {ev.parent_a
                  ? <ParentChip m={ev.parent_a} onSelect={onSelect} />
                  : <span className="unknown">亲本 A：未知（空）</span>}
                {ev.cross_type === 'cross' && (
                  <>
                    <span className="cross-symbol">×</span>
                    {ev.parent_b
                      ? <ParentChip m={ev.parent_b} onSelect={onSelect} />
                      : <span className="unknown">亲本 B：未知（空）</span>}
                  </>
                )}
              </div>
              {ev.notes && <p className="muted small">{ev.notes}</p>}
            </>
          ) : (
            <p className="muted">原始亲本，无交配记录。</p>
          )}
          <h4>全部祖先（NetworkX 回溯）</h4>
          {m.ancestor_ids.length ? (
            <div className="progeny">
              {m.ancestor_ids.map((aid) => {
                const a = matById[aid]
                return a ? <ParentChip key={aid} m={a} onSelect={onSelect} /> : <span key={aid} className="code">#{aid}</span>
              })}
            </div>
          ) : <p className="muted small">无祖先</p>}
          {m.descendant_ids.length > 0 && (
            <>
              <h4>后代</h4>
              <div className="progeny">
                {m.descendant_ids.map((did) => {
                  const d = matById[did]
                  return d ? <ParentChip key={did} m={d} onSelect={onSelect} /> : null
                })}
              </div>
            </>
          )}
        </div>

        <div className="panel">
          <h3>试验小区</h3>
          {m.plots.length ? m.plots.map((p) => (
            <span key={p.id} className="chip">
              {p.plot_code} · 区组 {p.block} 位置 {p.position}
            </span>
          )) : <p className="muted">未布置小区</p>}

          <h3>性状观测（含补录）</h3>
          <table>
            <thead><tr><th>性状</th><th>状态</th><th>数值</th><th>观测日</th><th>来源</th></tr></thead>
            <tbody>
              {m.observations.map((o) => (
                <tr key={o.id} className={`status-${o.status}`}>
                  <td>{o.trait_name}</td>
                  <td><span className={`status-tag ${o.status}`}>{STATUS_LABEL[o.status]}</span></td>
                  <td>{o.value === null ? '—' : `${o.value} ${o.unit}`}</td>
                  <td className="small">{o.observed_on || '—'}</td>
                  <td className="small muted">{o.source_note || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <BackfillForm materialId={m.id} observations={m.observations} onSaved={reload} />
        </div>
      </div>
    </section>
  )
}

function BackfillForm({ materialId, observations, onSaved }) {
  const { data: traits } = useApi(() => api.traits(), [])
  const byTrait = Object.fromEntries(observations.map((o) => [o.trait_code, o]))
  const [traitCode, setTraitCode] = useState(traits?.[0]?.trait_code || '')
  const [status, setStatus] = useState('measured')
  const [value, setValue] = useState('')
  const [source, setSource] = useState('')
  const [msg, setMsg] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    if (traits?.length && !traitCode) setTraitCode(traits[0].trait_code)
  }, [traits])

  const existing = byTrait[traitCode]

  const submit = async (e) => {
    e.preventDefault()
    setMsg(''); setError('')
    try {
      await api.upsertObs(materialId, traitCode, {
        status,
        value: status === 'measured' ? Number(value) : null,
        source_note: source || null,
      })
      setMsg('已保存（补录/更新成功）')
      onSaved()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <form className="backfill" onSubmit={submit}>
      <h4>{existing ? '观测补录 / 更新' : '新增观测'}</h4>
      {existing && (
        <p className="small muted">
          当前：{STATUS_LABEL[existing.status]}
          {existing.value !== null ? ` / ${existing.value}` : ''}
          {existing.source_note ? ` / ${existing.source_note}` : ''}
        </p>
      )}
      <div className="row">
        <select value={traitCode} onChange={(e) => setTraitCode(e.target.value)}>
          {(traits || []).map((t) => <option key={t.id} value={t.trait_code}>{t.name}</option>)}
        </select>
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="measured">实测</option>
          <option value="untested">未测</option>
          <option value="dead">死亡</option>
        </select>
        {status === 'measured' && (
          <input required type="number" step="0.01" placeholder="真实数值" value={value}
                 onChange={(e) => setValue(e.target.value)} />
        )}
        <input placeholder="来源（如：补测表 R-xxxx）" value={source}
               onChange={(e) => setSource(e.target.value)} />
        <button type="submit">保存</button>
      </div>
      {msg && <span className="ok">{msg}</span>}
      {error && <span className="error">{error}</span>}
    </form>
  )
}
