const BASE = '/api'

async function req(path, options = {}) {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      detail = (await res.json()).detail
    } catch {
      /* ignore */
    }
    throw new Error(detail)
  }
  return res.status === 204 ? null : res.json()
}

export const api = {
  health: () => req('/health'),
  materials: (q = '') => req(`/materials${q ? `?q=${encodeURIComponent(q)}` : ''}`),
  material: (id) => req(`/materials/${id}`),
  createMaterial: (body) =>
    req('/materials', { method: 'POST', body: JSON.stringify(body) }),
  matings: () => req('/matings'),
  createMating: (body) =>
    req('/matings', { method: 'POST', body: JSON.stringify(body) }),
  familyMean: (id, traitCode = '') =>
    req(`/matings/${id}/mean${traitCode ? `?trait_code=${traitCode}` : ''}`),
  traits: () => req('/traits'),
  plots: () => req('/plots'),
  upsertObs: (materialId, traitCode, body) =>
    req(`/materials/${materialId}/observations/${traitCode}`, {
      method: 'PUT',
      body: JSON.stringify(body),
    }),
}
