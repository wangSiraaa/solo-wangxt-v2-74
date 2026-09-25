const BASE = "/api";

async function req(path, options = {}) {
  const r = await fetch(BASE + path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!r.ok) {
    let detail = r.statusText;
    try {
      const body = await r.json();
      detail = body.detail ? JSON.stringify(body.detail) : detail;
    } catch {}
    throw new Error(`${r.status}: ${detail}`);
  }
  return r.json();
}

export const api = {
  materials: () => req("/materials"),
  crosses: () => req("/crosses"),
  plots: () => req("/plots"),
  traits: () => req("/traits"),
  pedigree: (id) => req(`/materials/${id}/pedigree`),
  observations: (params = {}) =>
    req("/observations?" + new URLSearchParams(params)),
  familyMean: (crossId, trait) =>
    req(`/families/${crossId}/mean?` + new URLSearchParams({ trait })),
  createMaterial: (body) =>
    req("/materials", { method: "POST", body: JSON.stringify(body) }),
  createCross: (body) =>
    req("/crosses", { method: "POST", body: JSON.stringify(body) }),
  createObservation: (body) =>
    req("/observations", { method: "POST", body: JSON.stringify(body) }),
  patchObservation: (id, body) =>
    req(`/observations/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
};
