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

function getNodeIcon(nodeType) {
  switch (nodeType) {
    case "plan": return "📝";
    case "characters": return "🎭";
    case "prepare_shot": return "🎬";
    case "generate_shot": return "🎥";
    case "build_cards": return "📋";
    case "export": return "📦";
    default: return "⚙️";
  }
}

export function renderWorkflowDiagram(nodes, selectedNodeId) {
  if (!nodes?.length) {
    return `<div class="empty-state">暂无节点。</div>`;
  }
  
  let html = "";
  nodes.forEach((node, index) => {
    const nodeId = `${node.node_type}:${node.node_key}`;
    const isActive = nodeId === selectedNodeId;
    const statusClass = `status-${escapeHtml(String(node.status || "unknown").toLowerCase())}`;
    
    html += `
      <div 
        class="workflow-node ${isActive ? "active" : ""} ${statusClass}"
        data-action="select-node"
        data-node-type="${escapeHtml(node.node_type)}"
        data-node-key="${escapeHtml(node.node_key)}"
      >
        <div class="workflow-node-icon">${getNodeIcon(node.node_type)}</div>
        <div class="workflow-node-label">${escapeHtml(node.title)}</div>
        <div class="workflow-node-type">${escapeHtml(node.node_type)}</div>
      </div>
    `;
    
    if (index < nodes.length - 1) {
      // Add connecting edge
      const nextNode = nodes[index + 1];
      const isNextActiveOrDone = nextNode.status === "success" || nextNode.status === "running" || nextNode.status === "generated";
      html += `<div class="workflow-edge ${isNextActiveOrDone ? "active" : ""}"></div>`;
    }
  });
  
  return html;
}

export function renderNodeSummary(nodeDetail) {
  if (!nodeDetail) {
    return `<div class="empty-state">选择节点后查看详情。</div>`;
  }
  const node = nodeDetail.node;
  const payload = node.payload || {};
  const nodeType = node.node_type;
  
  let baseItems = [
    ["节点类型", nodeType],
    ["节点键", node.node_key],
    ["当前状态", node.status || "未知"],
    ["当前激活版本", node.active_version_id || "未激活"],
  ];

  // Customized details based on node type
  if (nodeType === "plan") {
    const episode = payload.episode || {};
    baseItems.push(["标题", episode.title || "未命名"]);
    baseItems.push(["核心卖点", episode.selling_points ? episode.selling_points.join(" / ") : "无"]);
    baseItems.push(["角色数量", payload.characters ? payload.characters.length : 0]);
    baseItems.push(["镜头数量", payload.shots ? payload.shots.length : 0]);
  } else if (nodeType === "characters") {
    const chars = payload.characters || [];
    baseItems.push(["角色总数", chars.length]);
    const generatedCount = chars.reduce((acc, char) => acc + (char.reference_assets ? char.reference_assets.length : 0), 0);
    baseItems.push(["已生成资产", generatedCount]);
  } else if (nodeType === "prepare_shot" || nodeType === "generate_shot") {
    const shot = payload.shot || null;
    if (shot) {
      baseItems.push(["镜头标题", shot.title || "未命名"]);
      baseItems.push(["镜头状态", shot.status || "pending"]);
      baseItems.push(["镜头时长", `${shot.duration_seconds || 0} 秒`]);
      if (shot.prompt) {
        baseItems.push(["Prompt", shot.prompt]);
      }
    }
  } else if (nodeType === "export") {
    baseItems.push(["导出资产数", payload.assets ? payload.assets.length : 0]);
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

function renderCreativePayload(nodeType, data) {
  if (!data) return `<div class="empty-state">暂无数据</div>`;

  try {
    if (nodeType === "plan") {
      const ep = data.episode || {};
      const chars = data.characters || [];
      const shots = data.shots || [];
      
      let html = `<div class="payload-section"><h3 class="payload-title">剧本大纲</h3>`;
      html += `<div class="payload-text"><strong>一句话故事：</strong>${escapeHtml(ep.logline || "无")}</div>`;
      html += `<div class="payload-text"><strong>视觉风格：</strong>${escapeHtml(ep.visual_style || "无")}</div>`;
      
      if (ep.selling_points && ep.selling_points.length) {
        html += `<div class="payload-tags"><strong>核心卖点：</strong>` + 
          ep.selling_points.map(sp => `<span class="chip">${escapeHtml(sp)}</span>`).join("") + 
          `</div>`;
      }
      html += `</div>`;

      if (chars.length) {
        html += `<div class="payload-section"><h3 class="payload-title">登场角色 (${chars.length})</h3>`;
        html += `<div class="payload-grid">` + chars.map(c => `
          <div class="payload-card">
            <strong>${escapeHtml(c.name)}</strong> <span class="muted">(${escapeHtml(c.character_id)})</span>
            <p class="payload-desc">${escapeHtml(c.description || "")}</p>
          </div>
        `).join("") + `</div></div>`;
      }

      if (shots.length) {
        html += `<div class="payload-section"><h3 class="payload-title">分镜规划 (${shots.length})</h3>`;
        html += `<div class="payload-grid">` + shots.map(s => `
          <div class="payload-card">
            <strong>${escapeHtml(s.shot_id)}</strong>
            <p class="payload-desc">${escapeHtml(s.description || "")}</p>
          </div>
        `).join("") + `</div></div>`;
      }
      return html;
    }

    if (nodeType === "characters") {
      const chars = Array.isArray(data) ? data : (data.characters || []);
      let html = `<div class="payload-grid">`;
      html += chars.map(c => `
        <div class="payload-card">
          <h3 class="payload-title" style="border:none; padding:0; margin-bottom:8px;">${escapeHtml(c.name)} <span class="muted" style="font-size:12px; font-weight:normal;">(${escapeHtml(c.character_id)})</span></h3>
          <div class="payload-text"><strong>设定：</strong>${escapeHtml(c.description || "无")}</div>
          <div class="payload-text"><strong>外观：</strong>${escapeHtml(c.appearance || "无")}</div>
        </div>
      `).join("");
      html += `</div>`;
      return html;
    }

    if (nodeType === "prepare_shot" || nodeType === "generate_shot") {
      const s = data.shot || data;
      return `
        <div class="payload-section">
          <h3 class="payload-title">${escapeHtml(s.title || s.shot_id || "镜头详情")}</h3>
          <div class="payload-text"><strong>画面描述：</strong>${escapeHtml(s.description || "无")}</div>
          <div class="payload-text"><strong>提示词 (Prompt)：</strong><br/><span class="prompt-text">${escapeHtml(s.prompt || "无")}</span></div>
          ${s.audio_prompt ? `<div class="payload-text"><strong>音频提示词：</strong><br/><span class="prompt-text">${escapeHtml(s.audio_prompt)}</span></div>` : ""}
          <div class="payload-text"><strong>时长：</strong>${escapeHtml(s.duration_seconds || 0)} 秒</div>
        </div>
      `;
    }

    if (nodeType === "build_cards") {
      const cards = Array.isArray(data) ? data : (data.workflow_cards || []);
      let html = `<div class="payload-grid">`;
      html += cards.map(c => `
        <div class="payload-card">
          <strong>${escapeHtml(c.card_id)}</strong>
          <div class="payload-text" style="margin-top:8px;"><strong>动作：</strong><span class="chip">${escapeHtml(c.action)}</span></div>
          <div class="payload-text"><strong>目标镜头：</strong>${escapeHtml(c.shot_id || "无")}</div>
        </div>
      `).join("");
      html += `</div>`;
      return html;
    }

    if (nodeType === "export") {
      const manifest = data.manifest || {};
      return `
        <div class="payload-section">
          <h3 class="payload-title">导出清单</h3>
          <div class="payload-text"><strong>项目名称：</strong>${escapeHtml(manifest.project_name || "无")}</div>
          <div class="payload-text"><strong>导出状态：</strong>${renderStatusBadge(manifest.status)}</div>
          <div class="payload-text"><strong>包含角色数：</strong>${escapeHtml(manifest.total_characters || 0)}</div>
          <div class="payload-text"><strong>包含镜头数：</strong>${escapeHtml(manifest.total_shots || 0)}</div>
        </div>
      `;
    }

    // Fallback for unknown types
    return `<div class="payload-section"><div class="payload-text">暂无针对此节点类型的可视化展示。</div></div>`;
  } catch (e) {
    return `<div class="empty-state">数据解析失败</div>`;
  }
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
    <div class="creative-payload">
      ${renderCreativePayload(nodeDetail.node.node_type, payloadObject)}
    </div>
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
