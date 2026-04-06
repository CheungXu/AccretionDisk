const state = {
  projects: [],
  selectedProjectId: null,
  projectDetail: null,
  selectedNodeId: null,
  nodeDetail: null,
  inspectedVersionDetail: null,
  selectedRunDetail: null,
  executingNodeId: null,
  executingNodeTitle: "",
  workflowRunning: false,
  loading: false,
};

const listeners = new Set();

export function getState() {
  return state;
}

export function subscribe(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function setState(partialState) {
  Object.assign(state, partialState);
  for (const listener of listeners) {
    listener(state);
  }
}

export function resetNodeState() {
  setState({
    selectedNodeId: null,
    nodeDetail: null,
    inspectedVersionDetail: null,
    selectedRunDetail: null,
  });
}
