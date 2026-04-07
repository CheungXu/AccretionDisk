import {
  activateVersion,
  fetchNodeDetail,
  fetchProjectDetail,
  fetchProjects,
  fetchRunDetail,
  fetchVersionDetail,
  importProject,
  pickProjectDirectory,
  runNode,
} from "/services/api.js";
import {
  buildSourceVersionOptions,
  getNodeRunFormConfig,
  renderLog,
  renderMediaGallery,
  renderWorkflowDiagram,
  renderNodePayload,
  renderNodeSummary,
  renderProjectHero,
  renderProjectList,
  renderProjectStats,
  renderRunList,
  renderUserInputFormFields,
  renderVersionList,
  shouldShowRunForm,
} from "/components/renderers.js";
import { getState, resetNodeState, setState, subscribe } from "/state/store.js";

const initialRoute = readInitialRoute();
let initialRouteNodeConsumed = false;

const elements = {
  importForm: document.getElementById("import-form"),
  projectRootDisplay: document.getElementById("project-root-display"),
  importModeSelect: document.getElementById("import-mode-select"),
  refreshProjectsButton: document.getElementById("refresh-projects-button"),
  projectList: document.getElementById("project-list"),
  projectTitle: document.getElementById("project-title"),
  projectSubtitle: document.getElementById("project-subtitle"),
  projectMeta: document.getElementById("project-meta"),
  projectStats: document.getElementById("project-stats"),
  workflowDiagram: document.getElementById("workflow-diagram"),
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
  runWorkflowButton: document.getElementById("run-workflow-button"),
  finalOutputButton: document.getElementById("final-output-button"),
  workflowExecutionStatus: document.getElementById("workflow-execution-status"),
};

function readInitialRoute() {
  const query = new URLSearchParams(window.location.search);
  const projectId = query.get("project_id")?.trim() || null;
  const nodeType = query.get("node_type")?.trim() || null;
  const nodeKey = query.get("node_key")?.trim() || null;
  return {
    projectId,
    preferredNodeId: projectId && nodeType ? `${nodeType}:${nodeKey || "project"}` : null,
  };
}

function buildNodePageUrl(projectId, nodeType, nodeKey) {
  const query = new URLSearchParams({
    project_id: projectId,
    node_type: nodeType,
    node_key: nodeKey,
  });
  return `/pages/node.html?${query.toString()}`;
}

function normalizeWorkflowStatus(status) {
  return String(status || "").toLowerCase();
}

function isWorkflowNodeComplete(status) {
  return ["generated", "prompt_ready", "ready", "success"].includes(normalizeWorkflowStatus(status));
}

function findNextRunnableNode(projectDetail) {
  return (projectDetail?.nodes || []).find(
    (node) =>
      !["final_output", "script_storyboard"].includes(node.node_type) &&
      !isWorkflowNodeComplete(node.status) &&
      normalizeWorkflowStatus(node.status) !== "waiting"
  );
}

function setProjectRootDisplay(text, isSelected = false) {
  if (!elements.projectRootDisplay) {
    return;
  }
  elements.projectRootDisplay.textContent = text;
  elements.projectRootDisplay.classList.toggle("selected", isSelected);
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

function buildRunPayload(nodeDetail, options = {}) {
  const { userInputPayloadOverride = null } = options;
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
      user_input_payload: userInputPayloadOverride || readUserInputPayload(),
    };
  }
  return {
    ...basePayload,
    source_version_id: elements.sourceVersionSelect.value || null,
    extra_reference_count: Number(elements.extraReferenceInput.value || "0"),
    force: elements.forceRunInput.checked,
  };
}

function getFinalOutputNode(projectDetail) {
  return (projectDetail?.nodes || []).find((node) => node.node_type === "final_output") || null;
}

function canProduceFinalOutput(projectDetail) {
  const nodes = projectDetail?.nodes || [];
  if (!nodes.length) {
    return false;
  }
  return nodes
    .filter((node) => node.node_type !== "final_output")
    .every((node) => isWorkflowNodeComplete(node.status));
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

function getSelectedNodeParts() {
  const state = getState();
  if (!state.selectedNodeId) {
    return null;
  }
  const splitIndex = state.selectedNodeId.indexOf(":");
  return {
    nodeType: state.selectedNodeId.slice(0, splitIndex),
    nodeKey: state.selectedNodeId.slice(splitIndex + 1),
  };
}

function getPreferredProjectId(projects) {
  const state = getState();
  const candidateIds = [state.selectedProjectId, initialRoute.projectId, projects[0]?.project_id];
  return (
    candidateIds.find(
      (candidateId) => candidateId && projects.some((project) => project.project_id === candidateId)
    ) || null
  );
}

function getRoutePreferredNodeId(projectId) {
  if (initialRouteNodeConsumed) {
    return null;
  }
  if (!initialRoute.projectId || initialRoute.projectId !== projectId) {
    return null;
  }
  return initialRoute.preferredNodeId;
}

async function loadProjects() {
  setLoadingState(true);
  try {
    const projects = await fetchProjects();
    const selectedProjectId = getPreferredProjectId(projects);
    setState({ projects, selectedProjectId });
    if (selectedProjectId) {
      await loadProjectDetail(selectedProjectId);
    } else {
      resetNodeState();
      setState({
        projectDetail: null,
        inspectedVersionDetail: null,
        selectedRunDetail: null,
        executingNodeId: null,
        executingNodeTitle: "",
        workflowRunning: false,
      });
    }
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    setLoadingState(false);
  }
}

async function loadProjectDetail(projectId, preferredNodeId = null) {
  setLoadingState(true);
  try {
    const projectDetail = await fetchProjectDetail(projectId);
    const routePreferredNodeId = getRoutePreferredNodeId(projectId);
    const nextNodeId = resolveNextNodeId(
      projectDetail,
      preferredNodeId || routePreferredNodeId || getState().selectedNodeId
    );
    setState({
      selectedProjectId: projectId,
      projectDetail,
      inspectedVersionDetail: null,
      selectedRunDetail: null,
    });
    if (routePreferredNodeId && nextNodeId === routePreferredNodeId) {
      initialRouteNodeConsumed = true;
    }
    if (nextNodeId) {
      const [nodeType, nodeKey] = nextNodeId.split(":");
      await loadNodeDetail(projectId, nodeType, nodeKey);
    } else {
      resetNodeState();
    }
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    setLoadingState(false);
  }
}

function resolveNextNodeId(projectDetail, candidateNodeId) {
  const nodeIds = (projectDetail.nodes || []).map((node) => `${node.node_type}:${node.node_key}`);
  if (candidateNodeId && nodeIds.includes(candidateNodeId)) {
    return candidateNodeId;
  }
  return nodeIds[0] || null;
}

async function loadNodeDetail(projectId, nodeType, nodeKey) {
  setLoadingState(true);
  try {
    const nodeDetail = await fetchNodeDetail(projectId, nodeType, nodeKey);
    const selectedNodeId = `${nodeType}:${nodeKey}`;
    setState({
      selectedNodeId,
      nodeDetail,
      inspectedVersionDetail: null,
    });
    if (nodeDetail.runs?.length) {
      await loadRunDetail(projectId, nodeDetail.runs[0].run_id);
    } else {
      setState({ selectedRunDetail: null });
    }
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    setLoadingState(false);
  }
}

async function loadRunDetail(projectId, runId) {
  try {
    const selectedRunDetail = await fetchRunDetail(projectId, runId);
    setState({ selectedRunDetail });
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function loadVersionDetail(projectId, versionId) {
  try {
    const inspectedVersionDetail = await fetchVersionDetail(projectId, versionId);
    setState({ inspectedVersionDetail });
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function handleImportProject(event) {
  event.preventDefault();
  const importMode = elements.importModeSelect.value;
  setLoadingState(true);
  try {
    showToast("请在系统目录对话框中选择项目目录。", "info");
    const selection = await pickProjectDirectory();
    if (selection.cancelled) {
      return;
    }
    setProjectRootDisplay(selection.project_root, true);
    const projectRoot = selection.project_root;
    const importedProject = await importProject(projectRoot, importMode);
    showToast(
      `${selection.is_empty ? "已载入空项目" : "导入成功"}：${importedProject.display_name}`,
      "success"
    );
    await loadProjects();
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    setLoadingState(false);
  }
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
    showToast(`节点执行成功：${runPayload.version.version_id}`, "success");
    await loadProjectDetail(
      state.selectedProjectId,
      `${state.nodeDetail.node.node_type}:${state.nodeDetail.node.node_key}`
    );
    await loadRunDetail(state.selectedProjectId, runPayload.run.run_id);
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    setLoadingState(false);
  }
}

async function handleRunWorkflow() {
  const state = getState();
  if (!state.selectedProjectId || !state.projectDetail?.nodes?.length) {
    return;
  }

  const projectId = state.selectedProjectId;
  const initialSelectedNodeId = state.selectedNodeId;
  const initialUserInputPayload =
    initialSelectedNodeId === "user_input:project" ? readUserInputPayload() : null;
  elements.runWorkflowButton.disabled = true;
  elements.runWorkflowButton.textContent = "⏳ 工作流执行中...";
  setState({ workflowRunning: true });

  try {
    let executedCount = 0;
    while (true) {
      const latestProjectDetail = await fetchProjectDetail(projectId);
      setState({ projectDetail: latestProjectDetail });
      const nextNode = findNextRunnableNode(latestProjectDetail);
      if (!nextNode) {
        break;
      }

      const executingNodeId = `${nextNode.node_type}:${nextNode.node_key}`;
      setState({
        workflowRunning: true,
        executingNodeId,
        executingNodeTitle: nextNode.title,
      });
      showToast(`正在执行节点：${nextNode.title}...`, "info");

      let payload = null;
      const isInitialUserInputNode =
        nextNode.node_type === "user_input" && initialSelectedNodeId === executingNodeId;
      if (isInitialUserInputNode && getState().nodeDetail) {
        payload = buildRunPayload(getState().nodeDetail, {
          userInputPayloadOverride: initialUserInputPayload,
        });
      } else {
        await loadNodeDetail(projectId, nextNode.node_type, nextNode.node_key);
        payload = buildRunPayload(getState().nodeDetail);
      }

      await runNode(projectId, payload);
      executedCount += 1;
    }

    await loadProjectDetail(projectId, getState().selectedNodeId);
    showToast(
      executedCount > 0 ? "工作流执行完毕！" : "当前没有可执行的未完成节点。",
      executedCount > 0 ? "success" : "info"
    );
  } catch (error) {
    showToast(`工作流中断：${error.message}`, "error");
  } finally {
    elements.runWorkflowButton.disabled = false;
    elements.runWorkflowButton.textContent = "▶ 启动工作流";
    setState({
      workflowRunning: false,
      executingNodeId: null,
      executingNodeTitle: "",
    });
  }
}

async function handleProduceFinalOutput() {
  const state = getState();
  const finalOutputNode = getFinalOutputNode(state.projectDetail);
  if (!state.selectedProjectId || !finalOutputNode || !canProduceFinalOutput(state.projectDetail)) {
    return;
  }

  elements.finalOutputButton.disabled = true;
  setState({
    workflowRunning: true,
    executingNodeId: `${finalOutputNode.node_type}:${finalOutputNode.node_key}`,
    executingNodeTitle: finalOutputNode.title,
  });

  try {
    const runPayload = await runNode(state.selectedProjectId, {
      node_type: finalOutputNode.node_type,
      node_key: finalOutputNode.node_key,
      source_version_id: null,
      extra_reference_count: 0,
      force: true,
    });
    showToast("最终视频产出成功。", "success");
    await loadProjectDetail(
      state.selectedProjectId,
      `${finalOutputNode.node_type}:${finalOutputNode.node_key}`
    );
    await loadRunDetail(state.selectedProjectId, runPayload.run.run_id);
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    setState({
      workflowRunning: false,
      executingNodeId: null,
      executingNodeTitle: "",
    });
  }
}

async function handleActionClick(event) {
  const target = event.target.closest("[data-action]");
  if (!target) {
    return;
  }
  const action = target.dataset.action;
  const state = getState();

  if (action === "select-project") {
    await loadProjectDetail(target.dataset.projectId);
    return;
  }

  if (action === "select-node") {
    if (!state.selectedProjectId) {
      return;
    }
    
    // If the user is holding modifier keys (Cmd/Ctrl) or using middle click, 
    // let the browser handle it natively (open in new tab)
    if (event.metaKey || event.ctrlKey || event.button === 1) {
      return;
    }
    
    // Otherwise, prevent default navigation and do an in-page transition
    event.preventDefault();
    await loadNodeDetail(
      state.selectedProjectId,
      target.dataset.nodeType,
      target.dataset.nodeKey
    );
    
    // Update URL without reloading the page
    const url = new URL(target.href);
    window.history.pushState({}, "", url);
    return;
  }

  if (action === "inspect-run") {
    if (!state.selectedProjectId) {
      return;
    }
    await loadRunDetail(state.selectedProjectId, target.dataset.runId);
    return;
  }

  if (action === "inspect-version") {
    if (!state.selectedProjectId) {
      return;
    }
    await loadVersionDetail(state.selectedProjectId, target.dataset.versionId);
    return;
  }

  if (action === "activate-version") {
    if (!state.selectedProjectId) {
      return;
    }
    setLoadingState(true);
    try {
      await activateVersion(state.selectedProjectId, target.dataset.versionId);
      showToast("激活版本已切换。", "success");
      const nodeParts = getSelectedNodeParts();
      await loadProjectDetail(
        state.selectedProjectId,
        nodeParts ? `${nodeParts.nodeType}:${nodeParts.nodeKey}` : null
      );
    } catch (error) {
      showToast(error.message, "error");
    } finally {
      setLoadingState(false);
    }
  }
}

function renderWorkflowExecutionStatus(state) {
  if (!elements.workflowExecutionStatus) {
    return;
  }
  const isRunning = Boolean(state.workflowRunning && state.executingNodeTitle);
  elements.workflowExecutionStatus.className = `workflow-execution-status${isRunning ? " running" : ""}`;
  elements.workflowExecutionStatus.textContent = isRunning
    ? `正在执行：${state.executingNodeTitle}`
    : "当前暂无执行中的节点";
}

function renderFinalOutputButton(state) {
  if (!elements.finalOutputButton) {
    return;
  }

  const finalOutputNode = getFinalOutputNode(state.projectDetail);
  const hasProject = Boolean(state.selectedProjectId && finalOutputNode);
  elements.finalOutputButton.classList.toggle("hidden", !hasProject);
  if (!hasProject) {
    return;
  }

  const ready = canProduceFinalOutput(state.projectDetail);
  const alreadyProduced = isWorkflowNodeComplete(finalOutputNode.status);
  elements.finalOutputButton.disabled = !ready || state.workflowRunning;
  elements.finalOutputButton.textContent = alreadyProduced ? "重新产出最终视频" : "产出最终视频";
  elements.finalOutputButton.title = ready
    ? "将所有镜头视频按顺序合成为最终成片。"
    : "请先完成工作流中的所有前置节点。";
}

function renderApp(state) {
  elements.projectList.innerHTML = renderProjectList(state.projects, state.selectedProjectId);

  const hero = renderProjectHero(state.projectDetail);
  elements.projectTitle.textContent = hero.title;
  elements.projectSubtitle.textContent = hero.subtitle;
  elements.projectMeta.innerHTML = hero.metaHtml;
  
  if (state.selectedProjectId) {
    elements.runWorkflowButton.classList.remove("hidden");
    elements.runWorkflowButton.disabled = state.workflowRunning;
  } else {
    elements.runWorkflowButton.classList.add("hidden");
    elements.runWorkflowButton.disabled = false;
  }

  elements.projectStats.innerHTML = renderProjectStats(state.projectDetail);
  elements.workflowDiagram.innerHTML = renderWorkflowDiagram(
    state.projectDetail?.nodes || [],
    state.selectedNodeId,
    {
      executingNodeId: state.executingNodeId,
    }
  );
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
  renderWorkflowExecutionStatus(state);
  renderFinalOutputButton(state);

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
}

function bindEvents() {
  elements.importForm.addEventListener("submit", handleImportProject);
  elements.refreshProjectsButton.addEventListener("click", () => {
    void loadProjects();
  });
  elements.runNodeForm.addEventListener("submit", handleRunNode);
  elements.runWorkflowButton.addEventListener("click", handleRunWorkflow);
  elements.finalOutputButton.addEventListener("click", handleProduceFinalOutput);
  elements.projectList.addEventListener("click", (event) => {
    void handleActionClick(event);
  });
  elements.workflowDiagram.addEventListener("click", (event) => {
    void handleActionClick(event);
  });
  elements.versionList.addEventListener("click", (event) => {
    void handleActionClick(event);
  });
  elements.runList.addEventListener("click", (event) => {
    void handleActionClick(event);
  });
}

function main() {
  setProjectRootDisplay("点击下方按钮，通过系统目录选择器选择项目目录。");
  subscribe(renderApp);
  bindEvents();
  renderApp(getState());
  void loadProjects();
}

main();
