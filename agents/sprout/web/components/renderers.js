import { buildMediaUrl } from "/services/api.js";

const NODE_TYPE_LABELS = {
  user_input: "用户输入",
  characters: "角色资产",
  script_storyboard: "脚本分镜",
  prepare_shot: "提示词准备",
  generate_shot: "视频生成",
  build_cards: "执行卡",
  export: "项目导出",
  final_output: "最终成片",
};

const STATUS_LABELS = {
  ready: "已完成",
  generated: "已生成",
  success: "已完成",
  prompt_ready: "提示词已就绪",
  draft_ready: "输入已保存",
  running: "执行中",
  in_progress: "执行中",
  pending: "待执行",
  waiting: "等待上游",
  failed: "执行失败",
  error: "执行失败",
  draft: "草稿",
  bundle_only: "仅导入 Bundle",
  unknown: "未知",
};

const USER_INPUT_DEFAULTS = {
  topic: "",
  duration_seconds: 60,
  shot_count: 10,
  orientation: "9:16",
  visual_style: "",
  target_audience: "",
  notes: "",
  source_storyboard: "",
};

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

function normalizeStatus(status) {
  return String(status || "unknown").toLowerCase();
}

function formatStatusLabel(status) {
  const normalizedStatus = normalizeStatus(status);
  return STATUS_LABELS[normalizedStatus] || status || "未知";
}

function formatNodeTypeLabel(nodeType) {
  return NODE_TYPE_LABELS[nodeType] || nodeType || "未知节点";
}

function getShotVisualDescription(shot = {}) {
  return shot.visual_description || shot.description || "";
}

function getShotPromptText(shot = {}) {
  return shot.video_prompt || shot.prompt || shot.keyframe_prompt || "";
}

function getShotKeyframePrompt(shot = {}) {
  return shot.keyframe_prompt || "";
}

function getShotPreviewAssets(shots = []) {
  return shots.flatMap((shot) =>
    (shot.output_assets || []).filter(
      (asset) => asset.asset_type === "shot_keyframe" || asset.asset_type === "shot_image"
    )
  );
}

function normalizeUserInputPayload(payload = {}) {
  const topicInput = payload.topic_input || payload;
  return {
    topic: topicInput.topic || USER_INPUT_DEFAULTS.topic,
    duration_seconds:
      Number(topicInput.duration_seconds ?? USER_INPUT_DEFAULTS.duration_seconds) ||
      USER_INPUT_DEFAULTS.duration_seconds,
    shot_count:
      Number(topicInput.shot_count ?? USER_INPUT_DEFAULTS.shot_count) || USER_INPUT_DEFAULTS.shot_count,
    orientation: topicInput.orientation || USER_INPUT_DEFAULTS.orientation,
    visual_style: topicInput.visual_style || USER_INPUT_DEFAULTS.visual_style,
    target_audience: topicInput.target_audience || USER_INPUT_DEFAULTS.target_audience,
    notes: topicInput.notes || USER_INPUT_DEFAULTS.notes,
    source_storyboard: payload.source_storyboard || USER_INPUT_DEFAULTS.source_storyboard,
  };
}

function extractUserInputPayloadFromBundle(bundle = {}) {
  return normalizeUserInputPayload({
    topic_input: bundle.topic_input || {},
    source_storyboard: bundle.source_storyboard || "",
  });
}

export function getNodeRunFormConfig(nodeDetail) {
  if (!nodeDetail) {
    return {
      visible: false,
      showStandardControls: false,
      showUserInputFields: false,
      submitLabel: "执行当前节点",
    };
  }

  const nodeType = nodeDetail.node?.node_type;
  if (nodeType === "user_input") {
    return {
      visible: true,
      showStandardControls: false,
      showUserInputFields: true,
      submitLabel: "保存输入并生成规划",
    };
  }

  if (["characters", "prepare_shot", "generate_shot", "build_cards", "export"].includes(nodeType)) {
    return {
      visible: true,
      showStandardControls: true,
      showUserInputFields: false,
      submitLabel: "执行当前节点",
    };
  }

  return {
    visible: false,
    showStandardControls: false,
    showUserInputFields: false,
    submitLabel: "执行当前节点",
  };
}

export function renderUserInputFormFields(nodeDetail) {
  const inputPayload = normalizeUserInputPayload(nodeDetail?.node?.payload || {});
  return `
    <div class="form-row">
      <label class="field">
        <span>题材</span>
        <input name="topic" type="text" value="${escapeHtml(inputPayload.topic)}" placeholder="例如：古风逆袭短剧" />
      </label>
      <label class="field">
        <span>画幅</span>
        <input name="orientation" type="text" value="${escapeHtml(inputPayload.orientation)}" placeholder="例如：9:16" />
      </label>
    </div>
    <div class="form-row">
      <label class="field">
        <span>总时长（秒）</span>
        <input
          name="duration_seconds"
          type="number"
          value="${escapeHtml(inputPayload.duration_seconds)}"
          min="1"
        />
      </label>
      <label class="field">
        <span>镜头数</span>
        <input name="shot_count" type="number" value="${escapeHtml(inputPayload.shot_count)}" min="1" />
      </label>
    </div>
    <label class="field">
      <span>视觉风格</span>
      <textarea name="visual_style" rows="3" placeholder="例如：国漫古风条漫，厚涂，高对比，高张力">${escapeHtml(
        inputPayload.visual_style
      )}</textarea>
    </label>
    <label class="field">
      <span>目标受众</span>
      <input
        name="target_audience"
        type="text"
        value="${escapeHtml(inputPayload.target_audience)}"
        placeholder="例如：竖屏短剧用户"
      />
    </label>
    <label class="field">
      <span>补充说明</span>
      <textarea name="notes" rows="3" placeholder="补充设定、节奏要求或禁忌点">${escapeHtml(
        inputPayload.notes
      )}</textarea>
    </label>
    <label class="field">
      <span>已有分镜</span>
      <textarea
        name="source_storyboard"
        rows="8"
        placeholder="如填写已有分镜，将优先按分镜整理；留空则按题材规划。"
      >${escapeHtml(inputPayload.source_storyboard)}</textarea>
      <span class="field-help">留空时走题材规划；填写时走已有分镜整理。</span>
    </label>
  `;
}

function parseRuntimeIdTime(runtimeId) {
  const match = String(runtimeId || "").match(/_(\d{8})(\d{6})(\d{6})$/);
  if (!match) {
    return null;
  }
  const [, datePart, timePart] = match;
  return `${datePart.slice(0, 4)}-${datePart.slice(4, 6)}-${datePart.slice(6, 8)} ${timePart.slice(
    0,
    2
  )}:${timePart.slice(2, 4)}:${timePart.slice(4, 6)}`;
}

function formatVersionDisplay(versionId, createdAt = null) {
  if (createdAt) {
    return formatTime(createdAt);
  }
  return parseRuntimeIdTime(versionId) || versionId || "未命名版本";
}

function formatVersionSource(sourceVersionId) {
  if (!sourceVersionId) {
    return "当前项目状态";
  }
  return formatVersionDisplay(sourceVersionId);
}

function isCompletedStatus(status) {
  return ["generated", "prompt_ready", "ready", "success"].includes(normalizeStatus(status));
}

function renderStatusBadge(status, label = null) {
  const normalizedStatus = String(status || "unknown").toLowerCase();
  return `<span class="status-badge status-${escapeHtml(normalizedStatus)}">${escapeHtml(
    label || formatStatusLabel(status)
  )}</span>`;
}

function renderKeyValueList(items) {
  return items
    .map(
      (item) => {
        const normalizedItem = Array.isArray(item)
          ? { key: item[0], value: item[1], hint: "" }
          : item;
        return `
        <div class="meta-item">
          <span class="meta-key">${escapeHtml(normalizedItem.key)}</span>
          <span class="meta-value-group">
            <span class="meta-value">${escapeHtml(normalizedItem.value)}</span>
            ${
              normalizedItem.hint
                ? `<span class="meta-hint">${escapeHtml(normalizedItem.hint)}</span>`
                : ""
            }
          </span>
        </div>
      `;
      }
    )
    .join("");
}

function renderAssetPreview(projectId, asset) {
  if (!asset?.path) {
    return "";
  }
  const mediaUrl = buildMediaUrl(projectId, asset.path);
  if (asset.asset_type === "shot_video" || asset.asset_type === "final_video") {
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
    if (nodeDetail.node.node_type === "user_input") {
      return [];
    }
    if (nodeDetail.node.node_type === "script_storyboard") {
      return getShotPreviewAssets(bundle.shots || []);
    }
    if (nodeDetail.node.node_type === "characters") {
      return (bundle.characters || []).flatMap((character) => character.reference_assets || []);
    }
    if (nodeDetail.node.node_type === "export") {
      return bundle.assets || [];
    }
    if (nodeDetail.node.node_type === "final_output") {
      return bundle.assets.filter((asset) => asset.asset_type === "final_video");
    }
    if (nodeDetail.node.node_type === "build_cards") {
      return [];
    }
    const shot = (bundle.shots || []).find((item) => item.shot_id === nodeDetail.node.node_key);
    return shot?.output_assets || [];
  }

  const payload = nodeDetail.node.payload;
  if (nodeDetail.node.node_type === "user_input") {
    return [];
  }
  if (nodeDetail.node.node_type === "script_storyboard") {
    return getShotPreviewAssets(payload.shots || []);
  }
  if (nodeDetail.node.node_type === "characters") {
    return (payload.characters || []).flatMap((character) => character.reference_assets || []);
  }
  if (nodeDetail.node.node_type === "export") {
    return payload.assets || [];
  }
  if (nodeDetail.node.node_type === "final_output") {
    return payload.asset ? [payload.asset] : [];
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

export function renderNodeHero(projectDetail, nodeDetail) {
  if (!projectDetail || !nodeDetail) {
    return {
      title: "节点加载中",
      subtitle: "正在读取节点详情与版本关系。",
      metaHtml: "",
      statusHint: "",
    };
  }

  const node = nodeDetail.node;
  const project = projectDetail.project || {};
  const activeVersionText = node.active_version_id
    ? formatVersionDisplay(node.active_version_id)
    : "未激活";

  return {
    title: node.title || formatNodeTypeLabel(node.node_type),
    subtitle: `所属项目：${project.display_name || project.project_name || "未命名项目"}`,
    metaHtml: [
      renderStatusBadge(node.status),
      `<span class="chip">${escapeHtml(node.type_label || formatNodeTypeLabel(node.node_type))}</span>`,
      `<span class="chip">当前版本：${escapeHtml(activeVersionText)}</span>`,
    ].join(""),
    statusHint: node.status_reason || "节点状态会根据当前上游激活版本自动更新。",
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
    case "user_input": return "✍️";
    case "script_storyboard": return "🧾";
    case "plan": return "📝";
    case "characters": return "🎭";
    case "prepare_shot": return "🎬";
    case "generate_shot": return "🎥";
    case "build_cards": return "📋";
    case "export": return "📦";
    case "final_output": return "🎞️";
    default: return "⚙️";
  }
}

function renderWorkflowNodeCard(node, selectedNodeId, executingNodeId, extraClassName = "") {
  const nodeId = `${node.node_type}:${node.node_key}`;
  const isSelected = nodeId === selectedNodeId;
  const isExecuting = nodeId === executingNodeId;
  const statusClass = `status-${escapeHtml(normalizeStatus(node.status))}`;
  return `
    <div 
      class="workflow-node ${isSelected ? "selected" : ""} ${isExecuting ? "executing" : ""} ${statusClass} ${extraClassName}"
      data-action="select-node"
      data-node-type="${escapeHtml(node.node_type)}"
      data-node-key="${escapeHtml(node.node_key)}"
    >
      <div class="workflow-node-icon">${getNodeIcon(node.node_type)}</div>
      <div class="workflow-node-label">${escapeHtml(node.title)}</div>
      <div class="workflow-node-type">${escapeHtml(node.type_label || formatNodeTypeLabel(node.node_type))}</div>
      <div class="workflow-node-status">${renderStatusBadge(node.status)}</div>
    </div>
  `;
}

export function renderWorkflowDiagram(nodes, selectedNodeId, options = {}) {
  if (!nodes?.length) {
    return `<div class="empty-state">暂无节点。</div>`;
  }

  const executingNodeId = options.executingNodeId || null;
  const userInputNode = nodes.find((node) => node.node_type === "user_input") || null;
  const characterNode = nodes.find((node) => node.node_type === "characters") || null;
  const scriptStoryboardNode = nodes.find((node) => node.node_type === "script_storyboard") || null;
  const remainingNodes = nodes.filter(
    (node) => !["user_input", "characters", "script_storyboard"].includes(node.node_type)
  );

  if (!userInputNode || (!characterNode && !scriptStoryboardNode)) {
    let html = "";
    nodes.forEach((node, index) => {
      html += renderWorkflowNodeCard(node, selectedNodeId, executingNodeId);
      if (index < nodes.length - 1) {
        const nextNode = nodes[index + 1];
        const nextNodeId = `${nextNode.node_type}:${nextNode.node_key}`;
        const isNextActiveOrDone = isCompletedStatus(nextNode.status) || nextNodeId === executingNodeId;
        html += `<div class="workflow-edge ${isNextActiveOrDone ? "active" : ""}"></div>`;
      }
    });
    return html;
  }

  let html = renderWorkflowNodeCard(userInputNode, selectedNodeId, executingNodeId);
  const parallelStageActive = Boolean(
    (characterNode && isCompletedStatus(characterNode.status)) ||
      (scriptStoryboardNode && isCompletedStatus(scriptStoryboardNode.status))
  );
  html += `<div class="workflow-edge ${parallelStageActive ? "active" : ""}"></div>`;
  html += `<div class="workflow-parallel-stage">`;
  if (characterNode) {
    html += renderWorkflowNodeCard(characterNode, selectedNodeId, executingNodeId, "workflow-node-primary");
  }
  if (scriptStoryboardNode) {
    html += renderWorkflowNodeCard(
      scriptStoryboardNode,
      selectedNodeId,
      executingNodeId,
      "workflow-node-secondary"
    );
  }
  html += `</div>`;

  remainingNodes.forEach((node, index) => {
    const nodeId = `${node.node_type}:${node.node_key}`;
    const isNodeActiveOrDone = isCompletedStatus(node.status) || nodeId === executingNodeId;
    html += `<div class="workflow-edge ${isNodeActiveOrDone ? "active" : ""}"></div>`;
    html += renderWorkflowNodeCard(node, selectedNodeId, executingNodeId);
    if (index === remainingNodes.length - 1) {
      return;
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
    {
      key: "节点名称",
      value: node.title || formatNodeTypeLabel(nodeType),
    },
    {
      key: "节点类型",
      value: node.type_label || formatNodeTypeLabel(nodeType),
    },
    {
      key: "节点键",
      value: node.node_key,
    },
    {
      key: "当前状态",
      value: formatStatusLabel(node.status),
      hint: node.status_reason || "状态会跟随上游当前激活版本自动变化。",
    },
    {
      key: "当前激活版本",
      value: node.active_version_id ? formatVersionDisplay(node.active_version_id) : "未激活",
      hint: node.active_version_id ? `内部编号：${node.active_version_id}` : "当前还没有激活版本",
    },
  ];

  if (nodeType === "user_input") {
    const userInput = normalizeUserInputPayload(payload);
    baseItems.push({
      key: "输入模式",
      value: userInput.source_storyboard ? "已有分镜整理" : "题材规划",
    });
    baseItems.push({ key: "题材", value: userInput.topic || "未填写" });
    baseItems.push({ key: "总时长", value: `${userInput.duration_seconds} 秒` });
    baseItems.push({ key: "镜头数", value: userInput.shot_count });
    baseItems.push({ key: "画幅", value: userInput.orientation || "未填写" });
  } else if (nodeType === "script_storyboard") {
    const shots = payload.shots || [];
    const previewAssets = getShotPreviewAssets(shots);
    baseItems.push({ key: "剧本标题", value: payload.episode?.title || "未命名" });
    baseItems.push({ key: "剧情概述", value: payload.episode?.logline || "无" });
    baseItems.push({ key: "分镜数量", value: shots.length });
    baseItems.push({ key: "分镜图片", value: previewAssets.length });
  } else if (nodeType === "plan") {
    const episode = payload.episode || {};
    baseItems.push({ key: "标题", value: episode.title || "未命名" });
    baseItems.push({
      key: "核心卖点",
      value: episode.selling_points ? episode.selling_points.join(" / ") : "无",
    });
    baseItems.push({ key: "角色数量", value: payload.characters ? payload.characters.length : 0 });
    baseItems.push({ key: "镜头数量", value: payload.shots ? payload.shots.length : 0 });
  } else if (nodeType === "characters") {
    const chars = payload.characters || [];
    baseItems.push({ key: "角色总数", value: chars.length });
    const generatedCount = chars.reduce((acc, char) => acc + (char.reference_assets ? char.reference_assets.length : 0), 0);
    baseItems.push({ key: "已生成资产", value: generatedCount });
  } else if (nodeType === "prepare_shot" || nodeType === "generate_shot") {
    const shot = payload.shot || null;
    if (shot) {
      baseItems.push({ key: "镜头标题", value: shot.title || "未命名" });
      baseItems.push({ key: "镜头状态", value: formatStatusLabel(shot.status || "pending") });
      baseItems.push({ key: "镜头时长", value: `${shot.duration_seconds || 0} 秒` });
      if (getShotVisualDescription(shot)) {
        baseItems.push({ key: "画面描述", value: getShotVisualDescription(shot) });
      }
      if (getShotPromptText(shot)) {
        baseItems.push({ key: "视频提示词", value: getShotPromptText(shot) });
      }
    }
  } else if (nodeType === "export") {
    baseItems.push({ key: "导出资产数", value: payload.assets ? payload.assets.length : 0 });
  } else if (nodeType === "final_output") {
    baseItems.push({ key: "合成片段数", value: payload.segment_count || 0 });
    baseItems.push({ key: "已就绪片段", value: payload.completed_segments || 0 });
    baseItems.push({
      key: "最终视频",
      value: payload.asset?.path ? "已生成" : "未生成",
      hint: payload.asset?.path || payload.expected_path || "暂无输出路径",
    });
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
        const displayVersion = formatVersionDisplay(version.version_id, version.created_at);
        const sourceVersionText = formatVersionSource(version.source_version_id);
        return `
          <article class="stack-card">
            <div class="stack-card-header">
              <div class="stack-card-title-group">
                <strong class="stack-card-main">${escapeHtml(displayVersion)}</strong>
                <span class="stack-card-subtext">内部编号：${escapeHtml(version.version_id)}</span>
              </div>
              ${renderStatusBadge(version.status)}
            </div>
            <div class="stack-card-body">
              <span>创建时间：${escapeHtml(formatTime(version.created_at))}</span>
              <span>来源版本：${escapeHtml(sourceVersionText)}</span>
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
              <div class="stack-card-title-group">
                <strong class="stack-card-main">${escapeHtml(formatVersionDisplay(run.run_id, run.created_at))}</strong>
                <span class="stack-card-subtext">运行编号：${escapeHtml(run.run_id)}</span>
              </div>
              ${renderStatusBadge(run.status)}
            </div>
            <div class="stack-card-body">
              <span>创建时间：${escapeHtml(formatTime(run.created_at))}</span>
              <span>来源版本：${escapeHtml(formatVersionSource(run.source_version_id))}</span>
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
    if (nodeType === "user_input") {
      const inputPayload = normalizeUserInputPayload(data);
      const storyboardHtml = inputPayload.source_storyboard
        ? `
          <div class="payload-section">
            <h3 class="payload-title">已有分镜</h3>
            <div class="payload-text"><span class="prompt-text">${escapeHtml(
              inputPayload.source_storyboard
            )}</span></div>
          </div>
        `
        : "";
      return `
        <div class="payload-section">
          <h3 class="payload-title">用户输入</h3>
          <div class="payload-text"><strong>题材：</strong>${escapeHtml(inputPayload.topic || "未填写")}</div>
          <div class="payload-text"><strong>总时长：</strong>${escapeHtml(inputPayload.duration_seconds)} 秒</div>
          <div class="payload-text"><strong>镜头数：</strong>${escapeHtml(inputPayload.shot_count)}</div>
          <div class="payload-text"><strong>画幅：</strong>${escapeHtml(inputPayload.orientation || "未填写")}</div>
          <div class="payload-text"><strong>视觉风格：</strong>${escapeHtml(
            inputPayload.visual_style || "未填写"
          )}</div>
          <div class="payload-text"><strong>目标受众：</strong>${escapeHtml(
            inputPayload.target_audience || "未填写"
          )}</div>
          <div class="payload-text"><strong>补充说明：</strong>${escapeHtml(inputPayload.notes || "无")}</div>
        </div>
        ${storyboardHtml}
      `;
    }

    if (nodeType === "script_storyboard") {
      const episode = data.episode || {};
      const shots = data.shots || [];
      const topicInput = data.topic_input || {};
      const sourceStoryboard = data.source_storyboard || "";
      const sourceStoryboardHtml = sourceStoryboard
        ? `
          <div class="payload-section">
            <h3 class="payload-title">原始脚本文本</h3>
            <div class="payload-text"><span class="prompt-text">${escapeHtml(sourceStoryboard)}</span></div>
          </div>
        `
        : "";
      return `
        <div class="payload-section">
          <h3 class="payload-title">剧情总览</h3>
          <div class="payload-text"><strong>标题：</strong>${escapeHtml(episode.title || "未命名")}</div>
          <div class="payload-text"><strong>一句话故事：</strong>${escapeHtml(episode.logline || "无")}</div>
          <div class="payload-text"><strong>核心冲突：</strong>${escapeHtml(episode.core_hook || "无")}</div>
          <div class="payload-text"><strong>视觉风格：</strong>${escapeHtml(
            episode.visual_style || topicInput.visual_style || "未填写"
          )}</div>
        </div>
        <div class="payload-section">
          <h3 class="payload-title">分镜脚本 (${shots.length})</h3>
          <div class="payload-grid">
            ${shots
              .map(
                (shot) => `
                  <div class="payload-card">
                    <strong>${escapeHtml(shot.title || shot.shot_id || "未命名镜头")}</strong>
                    <div class="payload-text"><strong>画面描述：</strong>${escapeHtml(
                      getShotVisualDescription(shot) || "无"
                    )}</div>
                    <div class="payload-text"><strong>台词：</strong>${escapeHtml(shot.dialogue || "无")}</div>
                    <div class="payload-text"><strong>镜头语言：</strong>${escapeHtml(
                      shot.camera_language || "无"
                    )}</div>
                    <div class="payload-text"><strong>情绪：</strong>${escapeHtml(shot.emotion || "无")}</div>
                  </div>
                `
              )
              .join("")}
          </div>
        </div>
        ${sourceStoryboardHtml}
      `;
    }

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
            <p class="payload-desc">${escapeHtml(c.summary || c.role || "")}</p>
          </div>
        `).join("") + `</div></div>`;
      }

      if (shots.length) {
        html += `<div class="payload-section"><h3 class="payload-title">分镜规划 (${shots.length})</h3>`;
        html += `<div class="payload-grid">` + shots.map(s => `
          <div class="payload-card">
            <strong>${escapeHtml(s.shot_id)}</strong>
            <p class="payload-desc">${escapeHtml(getShotVisualDescription(s) || "")}</p>
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
          <div class="payload-text"><strong>设定：</strong>${escapeHtml(c.summary || c.role || "无")}</div>
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
          <div class="payload-text"><strong>画面描述：</strong>${escapeHtml(
            getShotVisualDescription(s) || "无"
          )}</div>
          <div class="payload-text"><strong>首帧提示词：</strong><br/><span class="prompt-text">${escapeHtml(
            getShotKeyframePrompt(s) || "无"
          )}</span></div>
          <div class="payload-text"><strong>视频提示词：</strong><br/><span class="prompt-text">${escapeHtml(
            getShotPromptText(s) || "无"
          )}</span></div>
          <div class="payload-text"><strong>台词：</strong>${escapeHtml(s.dialogue || "无")}</div>
          <div class="payload-text"><strong>音效：</strong>${escapeHtml(s.sound_effects || "无")}</div>
          <div class="payload-text"><strong>镜头语言：</strong>${escapeHtml(s.camera_language || "无")}</div>
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

    if (nodeType === "final_output") {
      const report = data.resolution_report || null;
      const reportSummary = report?.resolution_summary?.length
        ? `<div class="payload-text"><strong>分辨率分布：</strong>${escapeHtml(
            report.resolution_summary.map((item) => `${item.label}（${item.count} 段）`).join("；")
          )}</div>`
        : "";
      const reportWarnings = report?.warnings?.length
        ? `<div class="payload-text"><strong>适配说明：</strong>${escapeHtml(report.warnings.join("；"))}</div>`
        : "";
      const segmentDetails = report?.segments?.length
        ? `
          <div class="payload-section">
            <h3 class="payload-title">片段分辨率明细</h3>
            <div class="payload-grid">
              ${report.segments
                .map(
                  (segment) => `
                    <div class="payload-card">
                      <strong>${escapeHtml(segment.file_name || segment.shot_id || "未命名片段")}</strong>
                      <div class="payload-text"><strong>分辨率：</strong>${escapeHtml(
                        segment.resolution_label || "未知"
                      )}</div>
                      <div class="payload-text"><strong>适配模式：</strong>${escapeHtml(
                        segment.scale_mode || "未知"
                      )}</div>
                      <div class="payload-text"><strong>黑边适配：</strong>${escapeHtml(
                        segment.needs_padding ? "是" : "否"
                      )}</div>
                    </div>
                  `
                )
                .join("")}
            </div>
          </div>
        `
        : "";
      return `
        <div class="payload-section">
          <h3 class="payload-title">最终成片</h3>
          <div class="payload-text"><strong>合成片段：</strong>${escapeHtml(data.segment_count || 0)} 段</div>
          <div class="payload-text"><strong>已就绪片段：</strong>${escapeHtml(data.completed_segments || 0)} 段</div>
          <div class="payload-text"><strong>目标分辨率：</strong>${escapeHtml(
            report?.target_render_size?.label || "待统计"
          )}</div>
          <div class="payload-text"><strong>输出路径：</strong>${escapeHtml(
            data.asset?.path || data.expected_path || "尚未生成"
          )}</div>
          ${reportSummary}
          ${reportWarnings}
        </div>
        ${segmentDetails}
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
  if (nodeDetail.node.node_type === "user_input") {
    payloadObject = inspectedVersionDetail?.bundle
      ? extractUserInputPayloadFromBundle(inspectedVersionDetail.bundle)
      : normalizeUserInputPayload(nodeDetail.node.payload || {});
  } else if (nodeDetail.node.node_type === "script_storyboard") {
    payloadObject = inspectedVersionDetail?.bundle
      ? {
          topic_input: inspectedVersionDetail.bundle.topic_input || {},
          source_storyboard: inspectedVersionDetail.bundle.source_storyboard || "",
          episode: inspectedVersionDetail.bundle.episode || {},
          characters: inspectedVersionDetail.bundle.characters || [],
          shots: inspectedVersionDetail.bundle.shots || [],
        }
      : nodeDetail.node.payload || {};
  } else if (nodeDetail.node.node_type === "characters" && payloadSource.characters) {
    payloadObject = payloadSource.characters;
  } else if (nodeDetail.node.node_type === "build_cards" && payloadSource.workflow_cards) {
    payloadObject = payloadSource.workflow_cards;
  } else if (nodeDetail.node.node_type === "export" && payloadSource.manifest) {
    payloadObject = {
      manifest: payloadSource.manifest,
      assets: payloadSource.assets || [],
    };
  } else if (nodeDetail.node.node_type === "final_output" && payloadSource.assets) {
    const finalAsset = (payloadSource.assets || []).find((asset) => asset.asset_type === "final_video") || null;
    payloadObject = {
      asset: finalAsset,
      expected_path: null,
      segment_count: payloadSource.shots ? payloadSource.shots.length : 0,
      completed_segments: (payloadSource.shots || []).filter((shot) =>
        (shot.output_assets || []).some((asset) => asset.asset_type === "shot_video")
      ).length,
      resolution_report: finalAsset?.metadata?.resolution_report || null,
    };
  } else if (payloadSource.shot) {
    payloadObject = payloadSource.shot;
  } else if (payloadSource.shots) {
    payloadObject = payloadSource.shots.find((shot) => shot.shot_id === nodeDetail.node.node_key) || payloadSource;
  }

  const inspectedTitle = inspectedVersionDetail?.version?.version_id
    ? `<div class="sub-panel-title">当前查看版本：${escapeHtml(
        formatVersionDisplay(
          inspectedVersionDetail.version.version_id,
          inspectedVersionDetail.version.created_at
        )
      )}<span class="sub-panel-hint">内部编号：${escapeHtml(
        inspectedVersionDetail.version.version_id
      )}</span></div>`
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
            `${formatVersionDisplay(version.version_id, version.created_at)} | ${formatStatusLabel(
              version.status
            )}`
          )}</option>`
      )
      .join("")
  );
}

export function shouldShowRunForm(nodeDetail) {
  if (!nodeDetail) {
    return false;
  }
  return ["user_input", "characters", "prepare_shot", "generate_shot", "build_cards", "export"].includes(
    nodeDetail.node.node_type
  );
}
