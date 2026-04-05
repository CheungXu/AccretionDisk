import { buildMediaUrl } from "/services/api.js";

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function formatTime(value) {
  if (!value) {
    return "未记录";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString("zh-CN", { hour12: false });
}

function renderStatusBadge(status) {
  const normalizedStatus = String(status || "unknown").toLowerCase();
  return `<span class="status-badge status-${escapeHtml(normalizedStatus)}">${escapeHtml(status || "unknown")}</span>`;
}

function renderKeyValueList(items) {
  return items
    .map(
      ([key, value]) => `
        <div class="meta-item">
          <span class="meta-key">${escapeHtml(key)}</span>
          <span class="meta-value">${escapeHtml(value)}</span>
        </div>
      `
    )
    .join("");
}

function renderAssetPreview(projectId, asset) {
  if (!asset?.path) {
    return "";
  }
  const mediaUrl = buildMediaUrl(projectId, asset.path);
  if (asset.asset_type === "shot_video") {
    return `
      <article class="media-card">
        <div class="media-card-header">
          <strong>${escapeHtml(asset.asset_id)}</strong>
          <span>${escapeHtml(asset.asset_type)}</span>
        </div>
        <video controls src="${mediaUrl}"></video>
      </article>
    `;
  }
  return `
    <article class="media-card">
      <div class="media-card-header">
        <strong>${escapeHtml(asset.asset_id)}</strong>
        <span>${escapeHtml(asset.asset_type)}</span>
      </div>
      <img src="${mediaUrl}" alt="${escapeHtml(asset.asset_id)}" />
    </article>
  `;
}

function collectAssetsForNode(nodeDetail, inspectedVersionDetail) {
  if (!nodeDetail) {
    return [];
  }
  const bundle = inspectedVersionDetail?.bundle;
  if (bundle) {
    if (nodeDetail.node.node_type === "characters") {
      return (bundle.characters || []).flatMap((character) => character.reference_assets || []);
    }
    if (nodeDetail.node.node_type === "export") {
      return bundle.assets || [];
    }
    if (nodeDetail.node.node_type === "build_cards") {
      return [];
    }
    const shot = (bundle.shots || []).find((item) => item.shot_id === nodeDetail.node.node_key);
    return shot?.output_assets || [];
  }

  const payload = nodeDetail.node.payload;
  if (nodeDetail.node.node_type === "characters") {
    return (payload.characters || []).flatMap((character) => character.reference_assets || []);
  }
  if (nodeDetail.node.node_type === "export") {
    return payload.assets || [];
  }
  if (nodeDetail.node.node_type === "build_cards") {
    return [];
  }
  return payload.shot?.output_assets || [];
}

export function renderProjectList(projects, selectedProjectId) {
  if (!projects.length) {
    return `<div class="empty-state">还没有已导入项目。</div>`;
  }
  return projects
    .map((project) => {
      const isActive = project.project_id === selectedProjectId;
      return `
        <button
          type="button"
          class="project-card ${isActive ? "active" : ""}"
          data-action="select-project"
          data-project-id="${escapeHtml(project.project_id)}"
        >
          <div class="project-card-header">
            <strong>${escapeHtml(project.display_name)}</strong>
            ${renderStatusBadge(project.health_status)}
          </div>
          <div class="project-card-body">
            <span>${escapeHtml(project.project_name)}</span>
            <span>${escapeHtml(project.project_type)}</span>
          </div>
        </button>
      `;
    })
    .join("");
}

export function renderProjectHero(projectDetail) {
  if (!projectDetail) {
    return {
      title: "请选择项目",
      subtitle: "导入 `sprout` 项目目录后，可查看节点、版本、日志与产物。",
      metaHtml: "",
    };
  }
  const { project, manifest, bundle } = projectDetail;
  const subtitle = bundle?.episode?.logline || project.display_name;
  const metaHtml = [
    renderStatusBadge(project.health_status),
    renderStatusBadge(manifest?.status || "draft"),
    `<span class="chip">${escapeHtml(project.project_type)}</span>`,
    `<span class="chip">${escapeHtml(project.import_mode)}</span>`,
  ].join("");
  return {
    title: project.display_name,
    subtitle,
    metaHtml,
  };
}

export function renderProjectStats(projectDetail) {
  if (!projectDetail) {
    return "";
  }
  const manifest = projectDetail.manifest || {};
  const stats = [
    ["角色数", manifest.total_characters ?? 0],
    ["镜头数", manifest.total_shots ?? 0],
    ["角色资产", manifest.generated_character_assets ?? 0],
    ["镜头产物", manifest.generated_shot_assets ?? 0],
    ["执行卡", manifest.generated_workflow_cards ?? 0],
  ];
  return stats
    .map(
      ([label, value]) => `
        <article class="stat-card">
          <span class="stat-label">${escapeHtml(label)}</span>
          <strong class="stat-value">${escapeHtml(value)}</strong>
        </article>
      `
    )
    .join("");
}

export function renderNodeList(nodes, selectedNodeId) {
  if (!nodes?.length) {
    return `<div class="empty-state">暂无节点。</div>`;
  }
  return nodes
    .map((node) => {
      const nodeId = `${node.node_type}:${node.node_key}`;
      return `
        <button
          type="button"
          class="node-card ${nodeId === selectedNodeId ? "active" : ""}"
          data-action="select-node"
          data-node-type="${escapeHtml(node.node_type)}"
          data-node-key="${escapeHtml(node.node_key)}"
        >
          <div class="node-card-header">
            <strong>${escapeHtml(node.title)}</strong>
            ${renderStatusBadge(node.status)}
          </div>
          <div class="node-card-footer">
            <span>${escapeHtml(node.node_type)}</span>
            <span>版本：${escapeHtml(node.version_ids?.length ?? 0)}</span>
          </div>
        </button>
      `;
    })
    .join("");
}

export function renderNodeSummary(nodeDetail) {
  if (!nodeDetail) {
    return `<div class="empty-state">选择节点后查看详情。</div>`;
  }
  const node = nodeDetail.node;
  const payload = node.payload || {};
  const shot = payload.shot || null;
  const baseItems = [
    ["节点类型", node.node_type],
    ["节点键", node.node_key],
    ["当前激活版本", node.active_version_id || "未激活"],
  ];
  if (shot) {
    baseItems.push(["镜头标题", shot.title || "未命名"]);
    baseItems.push(["镜头状态", shot.status || "pending"]);
    baseItems.push(["镜头时长", `${shot.duration_seconds || 0} 秒`]);
  }
  return `
    <div class="meta-list">
      ${renderKeyValueList(baseItems)}
    </div>
  `;
}

export function renderVersionList(nodeDetail) {
  if (!nodeDetail?.versions?.length) {
    return `<div class="empty-state">暂无版本记录。</div>`;
  }
  return `
    <div class="sub-panel-title">版本列表</div>
    ${nodeDetail.versions
      .map((version) => {
        const isActive = version.version_id === nodeDetail.node.active_version_id;
        return `
          <article class="stack-card">
            <div class="stack-card-header">
              <strong>${escapeHtml(version.version_id)}</strong>
              ${renderStatusBadge(version.status)}
            </div>
            <div class="stack-card-body">
              <span>创建时间：${escapeHtml(formatTime(version.created_at))}</span>
              <span>来源版本：${escapeHtml(version.source_version_id || "无")}</span>
            </div>
            <div class="stack-card-actions">
              <button
                type="button"
                class="ghost-button"
                data-action="inspect-version"
                data-version-id="${escapeHtml(version.version_id)}"
              >
                查看版本
              </button>
              <button
                type="button"
                class="${isActive ? "secondary-button" : "primary-button"}"
                data-action="activate-version"
                data-version-id="${escapeHtml(version.version_id)}"
                ${isActive ? "disabled" : ""}
              >
                ${isActive ? "当前激活" : "切换为激活版本"}
              </button>
            </div>
          </article>
        `;
      })
      .join("")}
  `;
}

export function renderRunList(nodeDetail, selectedRunId) {
  if (!nodeDetail?.runs?.length) {
    return `<div class="empty-state">暂无运行记录。</div>`;
  }
  return `
    <div class="sub-panel-title">运行记录</div>
    ${nodeDetail.runs
      .map(
        (run) => `
          <article class="stack-card ${selectedRunId === run.run_id ? "active" : ""}">
            <div class="stack-card-header">
              <strong>${escapeHtml(run.run_id)}</strong>
              ${renderStatusBadge(run.status)}
            </div>
            <div class="stack-card-body">
              <span>创建时间：${escapeHtml(formatTime(run.created_at))}</span>
              <span>来源版本：${escapeHtml(run.source_version_id || "无")}</span>
            </div>
            <div class="stack-card-actions">
              <button
                type="button"
                class="ghost-button"
                data-action="inspect-run"
                data-run-id="${escapeHtml(run.run_id)}"
              >
                查看日志
              </button>
            </div>
          </article>
        `
      )
      .join("")}
  `;
}

export function renderNodePayload(nodeDetail, inspectedVersionDetail) {
  if (!nodeDetail) {
    return `<div class="empty-state">暂无内容。</div>`;
  }
  const payloadSource = inspectedVersionDetail?.bundle
    ? inspectedVersionDetail.bundle
    : nodeDetail.node.payload;

  let payloadObject = payloadSource;
  if (nodeDetail.node.node_type === "characters" && payloadSource.characters) {
    payloadObject = payloadSource.characters;
  } else if (nodeDetail.node.node_type === "build_cards" && payloadSource.workflow_cards) {
    payloadObject = payloadSource.workflow_cards;
  } else if (nodeDetail.node.node_type === "export" && payloadSource.manifest) {
    payloadObject = {
      manifest: payloadSource.manifest,
      assets: payloadSource.assets || [],
    };
  } else if (payloadSource.shot) {
    payloadObject = payloadSource.shot;
  } else if (payloadSource.shots) {
    payloadObject = payloadSource.shots.find((shot) => shot.shot_id === nodeDetail.node.node_key) || payloadSource;
  }

  const inspectedTitle = inspectedVersionDetail?.version?.version_id
    ? `<div class="sub-panel-title">当前查看版本：${escapeHtml(inspectedVersionDetail.version.version_id)}</div>`
    : "";

  return `
    ${inspectedTitle}
    <pre class="json-box">${escapeHtml(JSON.stringify(payloadObject, null, 2))}</pre>
  `;
}

export function renderMediaGallery(projectId, nodeDetail, inspectedVersionDetail) {
  const assets = collectAssetsForNode(nodeDetail, inspectedVersionDetail);
  if (!assets.length) {
    return `<div class="empty-state">暂无可预览媒体。</div>`;
  }
  return assets.map((asset) => renderAssetPreview(projectId, asset)).join("");
}

export function renderLog(runDetail) {
  if (!runDetail?.log) {
    return "暂无日志。";
  }
  return runDetail.log;
}

export function buildSourceVersionOptions(nodeDetail) {
  const baseOption = `<option value="">使用当前激活版本</option>`;
  if (!nodeDetail?.versions?.length) {
    return baseOption;
  }
  return (
    baseOption +
    nodeDetail.versions
      .map(
        (version) =>
          `<option value="${escapeHtml(version.version_id)}">${escapeHtml(
            `${version.version_id} | ${formatTime(version.created_at)}`
          )}</option>`
      )
      .join("")
  );
}

export function shouldShowRunForm(nodeDetail) {
  if (!nodeDetail) {
    return false;
  }
  return ["characters", "prepare_shot", "generate_shot", "build_cards", "export"].includes(
    nodeDetail.node.node_type
  );
}
