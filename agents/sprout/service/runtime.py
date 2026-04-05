"""Sprout 运行时记录与版本快照。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..core.models import SproutProjectBundle
from ..core.shared import (
    ensure_directory,
    read_json_file,
    slugify_name,
    write_json_file,
)
from ..core.storage import SproutProjectStore
from .types import (
    SproutNodeVersionRecord,
    SproutRunRecord,
    build_runtime_id,
    utc_now_isoformat,
)


@dataclass
class SproutRunStore:
    """记录节点执行状态与日志。"""

    def start_run(
        self,
        *,
        project_root: str | Path,
        project_id: str,
        node_type: str,
        node_key: str,
        source_version_id: str | None = None,
        shot_ids: list[str] | None = None,
    ) -> SproutRunRecord:
        runtime_root = self._ensure_runtime_root(project_root)
        run_id = build_runtime_id(
            f"run_{slugify_name(node_type, default_prefix='node')}_{slugify_name(node_key, default_prefix='key')}"
        )
        log_path = runtime_root / "logs" / f"{run_id}.log"
        run_record = SproutRunRecord(
            run_id=run_id,
            project_id=project_id,
            node_type=node_type,
            node_key=node_key,
            log_path=str(log_path),
            source_version_id=source_version_id,
            shot_ids=shot_ids or [],
        )
        self._write_run_record(project_root, run_record)
        self.append_log(project_root=project_root, run_record=run_record, message="开始执行节点。")
        return run_record

    def append_log(
        self,
        *,
        project_root: str | Path,
        run_record: SproutRunRecord,
        message: str,
    ) -> None:
        log_path = Path(run_record.log_path)
        ensure_directory(log_path.parent)
        current_content = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
        next_line = f"[{utc_now_isoformat()}] {message}\n"
        log_path.write_text(current_content + next_line, encoding="utf-8")
        run_record.updated_at = utc_now_isoformat()
        self._write_run_record(project_root, run_record)

    def finish_run(
        self,
        *,
        project_root: str | Path,
        run_record: SproutRunRecord,
        status: str,
        result_version_id: str | None = None,
        error_message: str | None = None,
    ) -> SproutRunRecord:
        run_record.status = status
        run_record.result_version_id = result_version_id
        run_record.error_message = error_message
        run_record.updated_at = utc_now_isoformat()
        self.append_log(
            project_root=project_root,
            run_record=run_record,
            message=f"节点执行结束，状态：{status}。",
        )
        if error_message:
            self.append_log(
                project_root=project_root,
                run_record=run_record,
                message=f"错误信息：{error_message}",
            )
        self._write_run_record(project_root, run_record)
        return run_record

    def get_run(self, project_root: str | Path, run_id: str) -> SproutRunRecord:
        record_path = self._ensure_runtime_root(project_root) / "runs" / f"{run_id}.json"
        payload = read_json_file(record_path)
        if not isinstance(payload, dict):
            raise ValueError(f"运行记录损坏：{record_path}")
        return SproutRunRecord.from_dict(payload)

    def list_runs(
        self,
        project_root: str | Path,
        *,
        node_type: str | None = None,
        node_key: str | None = None,
    ) -> list[SproutRunRecord]:
        runs_root = self._ensure_runtime_root(project_root) / "runs"
        run_records: list[SproutRunRecord] = []
        for run_path in sorted(runs_root.glob("*.json")):
            payload = read_json_file(run_path)
            if not isinstance(payload, dict):
                continue
            run_record = SproutRunRecord.from_dict(payload)
            if node_type and run_record.node_type != node_type:
                continue
            if node_key and run_record.node_key != node_key:
                continue
            run_records.append(run_record)
        return sorted(run_records, key=lambda item: item.created_at, reverse=True)

    def read_log(self, run_record: SproutRunRecord) -> str:
        log_path = Path(run_record.log_path)
        if not log_path.exists():
            return ""
        return log_path.read_text(encoding="utf-8")

    def _write_run_record(self, project_root: str | Path, run_record: SproutRunRecord) -> Path:
        runtime_root = self._ensure_runtime_root(project_root)
        return write_json_file(runtime_root / "runs" / f"{run_record.run_id}.json", run_record.to_dict())

    @staticmethod
    def _ensure_runtime_root(project_root: str | Path) -> Path:
        runtime_root = ensure_directory(Path(project_root).expanduser() / "runtime")
        ensure_directory(runtime_root / "runs")
        ensure_directory(runtime_root / "logs")
        ensure_directory(runtime_root / "versions")
        ensure_directory(runtime_root / "version_snapshots")
        return runtime_root


@dataclass
class SproutVersionStore:
    """记录节点版本快照与激活状态。"""

    project_store: SproutProjectStore | None = None

    def create_version(
        self,
        *,
        project_root: str | Path,
        project_bundle: SproutProjectBundle,
        project_id: str,
        node_type: str,
        node_key: str,
        source_version_id: str | None = None,
        run_id: str | None = None,
        shot_ids: list[str] | None = None,
        notes: list[str] | None = None,
    ) -> SproutNodeVersionRecord:
        runtime_root = SproutRunStore._ensure_runtime_root(project_root)
        version_id = build_runtime_id(
            f"version_{slugify_name(node_type, default_prefix='node')}_{slugify_name(node_key, default_prefix='key')}"
        )
        snapshot_path = runtime_root / "version_snapshots" / f"{version_id}_bundle.json"
        write_json_file(snapshot_path, project_bundle.to_dict())

        version_record = SproutNodeVersionRecord(
            version_id=version_id,
            project_id=project_id,
            node_type=node_type,
            node_key=node_key,
            bundle_snapshot_path=str(snapshot_path),
            source_version_id=source_version_id,
            run_id=run_id,
            asset_ids=self._collect_asset_ids(project_bundle, node_type=node_type, node_key=node_key),
            shot_ids=shot_ids or self._collect_shot_ids(project_bundle, node_type=node_type, node_key=node_key),
            notes=notes or [],
        )
        self._write_version_record(project_root, version_record)
        return version_record

    def list_versions(
        self,
        project_root: str | Path,
        *,
        node_type: str | None = None,
        node_key: str | None = None,
    ) -> list[SproutNodeVersionRecord]:
        versions_root = SproutRunStore._ensure_runtime_root(project_root) / "versions"
        version_records: list[SproutNodeVersionRecord] = []
        for version_path in sorted(versions_root.glob("*.json")):
            payload = read_json_file(version_path)
            if not isinstance(payload, dict):
                continue
            version_record = SproutNodeVersionRecord.from_dict(payload)
            if node_type and version_record.node_type != node_type:
                continue
            if node_key and version_record.node_key != node_key:
                continue
            version_records.append(version_record)
        return sorted(version_records, key=lambda item: item.created_at, reverse=True)

    def get_version(self, project_root: str | Path, version_id: str) -> SproutNodeVersionRecord:
        version_path = SproutRunStore._ensure_runtime_root(project_root) / "versions" / f"{version_id}.json"
        payload = read_json_file(version_path)
        if not isinstance(payload, dict):
            raise ValueError(f"版本记录损坏：{version_path}")
        return SproutNodeVersionRecord.from_dict(payload)

    def load_bundle_for_version(
        self,
        project_root: str | Path,
        version_id: str,
    ) -> SproutProjectBundle:
        version_record = self.get_version(project_root, version_id)
        return self._get_project_store().load_bundle(version_record.bundle_snapshot_path)

    def get_version_detail(
        self,
        project_root: str | Path,
        version_id: str,
    ) -> dict[str, Any]:
        version_record = self.get_version(project_root, version_id)
        bundle = self._get_project_store().load_bundle(version_record.bundle_snapshot_path)
        return {
            "version": version_record.to_dict(),
            "bundle": bundle.to_dict(),
        }

    def activate_version(
        self,
        *,
        project_root: str | Path,
        canonical_bundle_path: str | Path,
        version_id: str,
    ) -> dict[str, Any]:
        version_record = self.get_version(project_root, version_id)
        snapshot_payload = read_json_file(version_record.bundle_snapshot_path)
        if not isinstance(snapshot_payload, dict):
            raise ValueError("版本快照内容异常。")

        active_state = self.get_active_state(project_root)
        selected_versions = active_state.get("selected_versions", {})
        if not isinstance(selected_versions, dict):
            selected_versions = {}
        selected_versions[f"{version_record.node_type}:{version_record.node_key}"] = version_record.version_id
        next_state = {
            "active_bundle_version_id": version_record.version_id,
            "active_bundle_snapshot_path": version_record.bundle_snapshot_path,
            "selected_versions": selected_versions,
            "updated_at": utc_now_isoformat(),
        }
        write_json_file(self._get_active_state_path(project_root), next_state)
        write_json_file(canonical_bundle_path, snapshot_payload)
        return next_state

    def get_active_state(self, project_root: str | Path) -> dict[str, Any]:
        active_state_path = self._get_active_state_path(project_root)
        if not active_state_path.exists():
            return {
                "active_bundle_version_id": None,
                "active_bundle_snapshot_path": None,
                "selected_versions": {},
                "updated_at": None,
            }
        payload = read_json_file(active_state_path)
        return payload if isinstance(payload, dict) else {}

    def _write_version_record(self, project_root: str | Path, version_record: SproutNodeVersionRecord) -> Path:
        version_root = SproutRunStore._ensure_runtime_root(project_root) / "versions"
        return write_json_file(version_root / f"{version_record.version_id}.json", version_record.to_dict())

    @staticmethod
    def _get_active_state_path(project_root: str | Path) -> Path:
        return SproutRunStore._ensure_runtime_root(project_root) / "active_state.json"

    @staticmethod
    def _collect_shot_ids(
        project_bundle: SproutProjectBundle,
        *,
        node_type: str,
        node_key: str,
    ) -> list[str]:
        if node_type in {"prepare_shot", "generate_shot"}:
            return [node_key]
        return [shot.shot_id for shot in project_bundle.shots]

    @staticmethod
    def _collect_asset_ids(
        project_bundle: SproutProjectBundle,
        *,
        node_type: str,
        node_key: str,
    ) -> list[str]:
        if node_type == "characters":
            return [
                asset.asset_id
                for character in project_bundle.characters
                for asset in character.reference_assets
            ]
        if node_type in {"prepare_shot", "generate_shot"}:
            shot = project_bundle.find_shot(node_key)
            if shot is None:
                return []
            return [asset.asset_id for asset in shot.output_assets]
        return [asset.asset_id for asset in project_bundle.assets]

    def _get_project_store(self) -> SproutProjectStore:
        if self.project_store is None:
            self.project_store = SproutProjectStore()
        return self.project_store
