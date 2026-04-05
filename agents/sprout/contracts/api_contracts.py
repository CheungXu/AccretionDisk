"""Sprout API 共享契约常量。"""

SUPPORTED_NODE_TYPES = (
    "characters",
    "prepare_shot",
    "generate_shot",
    "build_cards",
    "export",
)

API_ENDPOINTS = {
    "health": {"method": "GET", "path": "/api/health"},
    "list_projects": {"method": "GET", "path": "/api/projects"},
    "import_project": {"method": "POST", "path": "/api/projects/import"},
    "project_detail": {"method": "GET", "path": "/api/projects/{project_id}"},
    "node_detail": {
        "method": "GET",
        "path": "/api/projects/{project_id}/nodes/detail?node_type={node_type}&node_key={node_key}",
    },
    "run_node": {"method": "POST", "path": "/api/projects/{project_id}/nodes/run"},
    "list_versions": {"method": "GET", "path": "/api/projects/{project_id}/versions"},
    "version_detail": {"method": "GET", "path": "/api/projects/{project_id}/versions/{version_id}"},
    "activate_version": {"method": "POST", "path": "/api/projects/{project_id}/activate"},
    "run_detail": {"method": "GET", "path": "/api/projects/{project_id}/runs/{run_id}"},
    "media": {"method": "GET", "path": "/api/projects/{project_id}/media?path={asset_path}"},
}
