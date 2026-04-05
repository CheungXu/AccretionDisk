const JSON_HEADERS = {
  "Content-Type": "application/json; charset=utf-8",
};

async function requestJson(path, options = {}) {
  const response = await fetch(path, options);
  const contentType = response.headers.get("Content-Type") || "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : await response.text();
  if (!response.ok) {
    const errorMessage =
      typeof payload === "object" && payload && "error" in payload
        ? payload.error
        : `请求失败：${response.status}`;
    throw new Error(errorMessage);
  }
  return payload;
}

export async function fetchProjects() {
  const payload = await requestJson("/api/projects");
  return payload.projects || [];
}

export async function importProject(projectRoot, importMode) {
  return requestJson("/api/projects/import", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({
      project_root: projectRoot,
      import_mode: importMode,
    }),
  });
}

export async function fetchProjectDetail(projectId) {
  return requestJson(`/api/projects/${encodeURIComponent(projectId)}`);
}

export async function fetchNodeDetail(projectId, nodeType, nodeKey) {
  const query = new URLSearchParams({
    node_type: nodeType,
    node_key: nodeKey,
  });
  return requestJson(`/api/projects/${encodeURIComponent(projectId)}/nodes/detail?${query.toString()}`);
}

export async function runNode(projectId, payload) {
  return requestJson(`/api/projects/${encodeURIComponent(projectId)}/nodes/run`, {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(payload),
  });
}

export async function activateVersion(projectId, versionId) {
  return requestJson(`/api/projects/${encodeURIComponent(projectId)}/activate`, {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ version_id: versionId }),
  });
}

export async function fetchRunDetail(projectId, runId) {
  return requestJson(`/api/projects/${encodeURIComponent(projectId)}/runs/${encodeURIComponent(runId)}`);
}

export async function fetchVersionDetail(projectId, versionId) {
  return requestJson(`/api/projects/${encodeURIComponent(projectId)}/versions/${encodeURIComponent(versionId)}`);
}

export function buildMediaUrl(projectId, assetPath) {
  const query = new URLSearchParams({ path: assetPath });
  return `/api/projects/${encodeURIComponent(projectId)}/media?${query.toString()}`;
}
