import {
  activateVersion,
  fetchNodeDetail,
  fetchProjectDetail,
  fetchRunDetail,
  fetchVersionDetail,
  runNode,
} from "/services/api.js";
import {
  buildSourceVersionOptions,
  getNodeRunFormConfig,
  renderLog,
  renderMediaGallery,
  renderNodeHero,
  renderNodePayload,
  renderNodeSummary,
  renderRunList,
  renderUserInputFormFields,
  renderVersionList,
  shouldShowRunForm,
} from "/components/renderers.js";
import { getState, setState, subscribe } from "/state/store.js";

const route = readRoute();

const elements = {
  backToWorkbench: document.getElementById("back-to-workbench"),
  nodeTitle: document.getElementById("node-title"),
  nodeSubtitle: document.getElementById("node-subtitle"),
  nodeMeta: document.getElementById("node-meta"),
  nodeStatusHint: document.getElementById("node-status-hint"),
  nodeSummary: document.getElementById("node-summary"),
  runNodeForm: document.getElementById("run-node-form"),
  standardRunOptions: document.getElementById("standard-run-options"),
  userInputFormFields: document.getElementById("user-input-form-fields"),
  sourceVersionSelect: document.getElementById("source-version-select"),
  extraReferenceInput: document.getElementById("extra-reference-input"),
  forceRunInput: document.getElementById("force-run-input"),
  runNodeButton: document.getElementById("run-node-button"),
  versionList: document.getElementById("version-list"),
  runList: document.getElementById("run-list"),
  nodePayload: document.getElementById("node-payload"),
  mediaGallery: document.getElementById("media-gallery"),
  runLog: document.getElementById("run-log"),
  toast: document.getElementById("toast"),
};

function readRoute() {
  const query = new URLSearchParams(window.location.search);
  return {
    projectId: query.get("project_id")?.trim() || null,
    nodeType: query.get("node_type")?.trim() || null,
    nodeKey: query.get("node_key")?.trim() || "project",
  };
}

function buildWorkbenchUrl(projectId, nodeType, nodeKey) {
  const query = new URLSearchParams({
    project_id: projectId,
    node_type: nodeType,
    node_key: nodeKey,
  });
  return `/pages/index.html?${query.toString()}`;
}

function showToast(message, type = "info") {
  elements.toast.textContent = message;
  elements.toast.className = `toast ${type}`;
  window.clearTimeout(showToast.timerId);
  showToast.timerId = window.setTimeout(() => {
    elements.toast.className = "toast hidden";
  }, 2800);
}

function setLoadingState(isLoading) {
  setState({ loading: isLoading });
  document.body.classList.toggle("loading", isLoading);
}

function readUserInputPayload() {
  const queryFieldValue = (name) =>
    elements.userInputFormFields?.querySelector(`[name="${name}"]`)?.value?.trim() || "";

  return {
    topic: queryFieldValue("topic"),
    duration_seconds: Number(queryFieldValue("duration_seconds") || "60"),
    shot_count: Number(queryFieldValue("shot_count") || "10"),
    orientation: queryFieldValue("orientation") || "9:16",
    visual_style: queryFieldValue("visual_style"),
    target_audience: queryFieldValue("target_audience"),
    notes: queryFieldValue("notes"),
    source_storyboard: queryFieldValue("source_storyboard"),
  };
}

function buildRunPayload(nodeDetail) {
  const basePayload = {
    node_type: nodeDetail.node.node_type,
    node_key: nodeDetail.node.node_key,
  };
  if (nodeDetail.node.node_type === "user_input") {
    return {
      ...basePayload,
      source_version_id: null,
      extra_reference_count: 0,
      force: false,
      user_input_payload: readUserInputPayload(),
    };
  }
  return {
    ...basePayload,
    source_version_id: elements.sourceVersionSelect.value || null,
    extra_reference_count: Number(elements.extraReferenceInput.value || "0"),
    force: elements.forceRunInput.checked,
  };
}

function updateBackLink(projectId, nodeType, nodeKey) {
  elements.backToWorkbench.href = buildWorkbenchUrl(projectId, nodeType, nodeKey);
}

async function loadRunDetail(projectId, runId) {
  const selectedRunDetail = await fetchRunDetail(projectId, runId);
  setState({ selectedRunDetail });
}

async function loadVersionDetail(projectId, versionId) {
  const inspectedVersionDetail = await fetchVersionDetail(projectId, versionId);
  setState({ inspectedVersionDetail });
}

async function loadNodePage(projectId, nodeType, nodeKey, options = {}) {
  setLoadingState(true);
  try {
    const [projectDetail, nodeDetail] = await Promise.all([
      fetchProjectDetail(projectId),
      fetchNodeDetail(projectId, nodeType, nodeKey),
    ]);
    let selectedRunDetail = null;
    if (options.preferredRunId) {
      selectedRunDetail = await fetchRunDetail(projectId, options.preferredRunId);
    } else if (nodeDetail.runs?.length) {
      selectedRunDetail = await fetchRunDetail(projectId, nodeDetail.runs[0].run_id);
    }

    setState({
      selectedProjectId: projectId,
      selectedNodeId: `${nodeType}:${nodeKey}`,
      projectDetail,
      nodeDetail,
      inspectedVersionDetail: null,
      selectedRunDetail,
    });
    updateBackLink(projectId, nodeType, nodeKey);
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    setLoadingState(false);
  }
}

async function refreshCurrentNode(options = {}) {
  const state = getState();
  const selectedNodeId = state.selectedNodeId;
  if (!state.selectedProjectId || !selectedNodeId) {
    return;
  }
  const [nodeType, nodeKey] = selectedNodeId.split(":");
  await loadNodePage(state.selectedProjectId, nodeType, nodeKey, options);
}

async function handleRunNode(event) {
  event.preventDefault();
  const state = getState();
  if (!state.selectedProjectId || !state.nodeDetail) {
    return;
  }

  setLoadingState(true);
  try {
    const payload = buildRunPayload(state.nodeDetail);
    const runPayload = await runNode(state.selectedProjectId, payload);
    showToast("节点执行成功。", "success");
    await refreshCurrentNode({ preferredRunId: runPayload.run.run_id });
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    setLoadingState(false);
  }
}

async function handleActionClick(event) {
  const target = event.target.closest("[data-action]");
  if (!target) {
    return;
  }
  const state = getState();
  if (!state.selectedProjectId) {
    return;
  }

  const action = target.dataset.action;
  if (action === "inspect-run") {
    try {
      await loadRunDetail(state.selectedProjectId, target.dataset.runId);
    } catch (error) {
      showToast(error.message, "error");
    }
    return;
  }

  if (action === "inspect-version") {
    try {
      await loadVersionDetail(state.selectedProjectId, target.dataset.versionId);
    } catch (error) {
      showToast(error.message, "error");
    }
    return;
  }

  if (action === "activate-version") {
    setLoadingState(true);
    try {
      await activateVersion(state.selectedProjectId, target.dataset.versionId);
      showToast("激活版本已切换。", "success");
      await refreshCurrentNode();
    } catch (error) {
      showToast(error.message, "error");
    } finally {
      setLoadingState(false);
    }
  }
}

function renderApp(state) {
  const hero = renderNodeHero(state.projectDetail, state.nodeDetail);
  elements.nodeTitle.textContent = hero.title;
  elements.nodeSubtitle.textContent = hero.subtitle;
  elements.nodeMeta.innerHTML = hero.metaHtml;
  elements.nodeStatusHint.textContent = hero.statusHint;
  elements.nodeStatusHint.classList.toggle("hidden", !hero.statusHint);
  elements.nodeSummary.innerHTML = renderNodeSummary(state.nodeDetail);
  elements.versionList.innerHTML = renderVersionList(state.nodeDetail);
  elements.runList.innerHTML = renderRunList(
    state.nodeDetail,
    state.selectedRunDetail?.run?.run_id || null
  );
  elements.nodePayload.innerHTML = renderNodePayload(state.nodeDetail, state.inspectedVersionDetail);
  elements.mediaGallery.innerHTML = renderMediaGallery(
    state.selectedProjectId,
    state.nodeDetail,
    state.inspectedVersionDetail
  );
  elements.runLog.textContent = renderLog(state.selectedRunDetail);

  const runFormVisible = shouldShowRunForm(state.nodeDetail);
  elements.runNodeForm.classList.toggle("hidden", !runFormVisible);
  if (runFormVisible) {
    const runFormConfig = getNodeRunFormConfig(state.nodeDetail);
    elements.standardRunOptions.classList.toggle("hidden", !runFormConfig.showStandardControls);
    elements.userInputFormFields.classList.toggle("hidden", !runFormConfig.showUserInputFields);
    elements.runNodeButton.textContent = runFormConfig.submitLabel;
    if (runFormConfig.showStandardControls) {
      elements.sourceVersionSelect.innerHTML = buildSourceVersionOptions(state.nodeDetail);
    }
    if (runFormConfig.showUserInputFields) {
      elements.userInputFormFields.innerHTML = renderUserInputFormFields(state.nodeDetail);
    } else {
      elements.userInputFormFields.innerHTML = "";
    }
  }

  document.title = `${hero.title} · Sprout 节点管理`;
}

function bindEvents() {
  elements.runNodeForm.addEventListener("submit", handleRunNode);
  elements.versionList.addEventListener("click", (event) => {
    void handleActionClick(event);
  });
  elements.runList.addEventListener("click", (event) => {
    void handleActionClick(event);
  });
}

function renderMissingRoute() {
  elements.nodeTitle.textContent = "缺少节点参数";
  elements.nodeSubtitle.textContent = "请从工作流管线点击节点进入节点管理页。";
  elements.nodeStatusHint.textContent = "";
  elements.nodeStatusHint.classList.add("hidden");
}

function main() {
  subscribe(renderApp);
  bindEvents();
  renderApp(getState());

  if (!route.projectId || !route.nodeType) {
    renderMissingRoute();
    return;
  }

  void loadNodePage(route.projectId, route.nodeType, route.nodeKey);
}

main();
