import {
  activateVersion,
  fetchNodeDetail,
  fetchProjectDetail,
  fetchProjects,
  fetchRunDetail,
  fetchVersionDetail,
  importProject,
  runNode,
} from "/services/api.js";
import {
  buildSourceVersionOptions,
  renderLog,
  renderMediaGallery,
  renderWorkflowDiagram,
  renderNodePayload,
  renderNodeSummary,
  renderProjectHero,
  renderProjectList,
  renderProjectStats,
  renderRunList,
  renderVersionList,
  shouldShowRunForm,
} from "/components/renderers.js";
import { getState, resetNodeState, setState, subscribe } from "/state/store.js";

const elements = {
  importForm: document.getElementById("import-form"),
  projectRootInput: document.getElementById("project-root-input"),
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
  sourceVersionSelect: document.getElementById("source-version-select"),
  extraReferenceInput: document.getElementById("extra-reference-input"),
  forceRunInput: document.getElementById("force-run-input"),
  versionList: document.getElementById("version-list"),
  runList: document.getElementById("run-list"),
  nodePayload: document.getElementById("node-payload"),
  mediaGallery: document.getElementById("media-gallery"),
  runLog: document.getElementById("run-log"),
  toast: document.getElementById("toast"),
  runWorkflowButton: document.getElementById("run-workflow-button"),
};

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

async function loadProjects() {
  setLoadingState(true);
  try {
    const projects = await fetchProjects();
    const state = getState();
    const selectedProjectId =
      state.selectedProjectId && projects.some((project) => project.project_id === state.selectedProjectId)
        ? state.selectedProjectId
        : projects[0]?.project_id || null;
    setState({ projects, selectedProjectId });
    if (selectedProjectId) {
      await loadProjectDetail(selectedProjectId);
    } else {
      resetNodeState();
      setState({
        projectDetail: null,
        inspectedVersionDetail: null,
        selectedRunDetail: null,
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
    const nextNodeId = resolveNextNodeId(projectDetail, preferredNodeId || getState().selectedNodeId);
    setState({
      selectedProjectId: projectId,
      projectDetail,
      inspectedVersionDetail: null,
      selectedRunDetail: null,
    });
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
  const projectRoot = elements.projectRootInput.value.trim();
  const importMode = elements.importModeSelect.value;
  if (!projectRoot) {
    showToast("请先填写项目目录。", "error");
    return;
  }
  setLoadingState(true);
  try {
    const importedProject = await importProject(projectRoot, importMode);
    showToast(`导入成功：${importedProject.display_name}`, "success");
    elements.importForm.reset();
    elements.importModeSelect.value = "reference";
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
    const payload = {
      node_type: state.nodeDetail.node.node_type,
      node_key: state.nodeDetail.node.node_key,
      source_version_id: elements.sourceVersionSelect.value || null,
      extra_reference_count: Number(elements.extraReferenceInput.value || "0"),
      force: elements.forceRunInput.checked,
    };
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
  
  const nodes = state.projectDetail.nodes;
  elements.runWorkflowButton.disabled = true;
  elements.runWorkflowButton.textContent = "⏳ 工作流执行中...";
  
  try {
    for (const node of nodes) {
      // Skip plan node as it usually requires manual input or is already done
      if (node.node_type === "plan") continue;
      
      showToast(`正在执行节点：${node.title}...`, "info");
      
      // Select the node to show progress
      await loadNodeDetail(state.selectedProjectId, node.node_type, node.node_key);
      
      const payload = {
        node_type: node.node_type,
        node_key: node.node_key,
        source_version_id: null,
        extra_reference_count: 0,
        force: false,
      };
      
      await runNode(state.selectedProjectId, payload);
      
      // Reload project detail to update workflow diagram status
      await loadProjectDetail(state.selectedProjectId, `${node.node_type}:${node.node_key}`);
    }
    
    showToast("工作流执行完毕！", "success");
  } catch (error) {
    showToast(`工作流中断：${error.message}`, "error");
  } finally {
    elements.runWorkflowButton.disabled = false;
    elements.runWorkflowButton.textContent = "▶ 启动工作流";
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
    await loadNodeDetail(
      state.selectedProjectId,
      target.dataset.nodeType,
      target.dataset.nodeKey
    );
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

function renderApp(state) {
  elements.projectList.innerHTML = renderProjectList(state.projects, state.selectedProjectId);

  const hero = renderProjectHero(state.projectDetail);
  elements.projectTitle.textContent = hero.title;
  elements.projectSubtitle.textContent = hero.subtitle;
  elements.projectMeta.innerHTML = hero.metaHtml;
  
  if (state.selectedProjectId) {
    elements.runWorkflowButton.classList.remove("hidden");
  } else {
    elements.runWorkflowButton.classList.add("hidden");
  }
  
  elements.projectStats.innerHTML = renderProjectStats(state.projectDetail);
  elements.workflowDiagram.innerHTML = renderWorkflowDiagram(state.projectDetail?.nodes || [], state.selectedNodeId);
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
    elements.sourceVersionSelect.innerHTML = buildSourceVersionOptions(state.nodeDetail);
  }
}

function bindEvents() {
  elements.importForm.addEventListener("submit", handleImportProject);
  elements.refreshProjectsButton.addEventListener("click", () => {
    void loadProjects();
  });
  elements.runNodeForm.addEventListener("submit", handleRunNode);
  elements.runWorkflowButton.addEventListener("click", handleRunWorkflow);
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
  subscribe(renderApp);
  bindEvents();
  renderApp(getState());
  void loadProjects();
}

main();
