"""Sprout 命令行入口。"""

from __future__ import annotations

import argparse
from pathlib import Path

from .core.project_store import SproutProjectStore
from .core.schema import SproutTopicInput
from .service import SproutProjectService, run_sprout_api_server
from .core.workflow import SproutWorkflow


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sprout AI 短剧工作流")
    subparsers = parser.add_subparsers(dest="command", required=True)

    _build_plan_topic_parser(subparsers)
    _build_plan_storyboard_parser(subparsers)
    _build_build_characters_parser(subparsers)
    _build_prepare_shots_parser(subparsers)
    _build_generate_shots_parser(subparsers)
    _build_build_cards_parser(subparsers)
    _build_export_parser(subparsers)
    _build_run_all_parser(subparsers)
    _build_import_project_parser(subparsers)
    _build_list_projects_parser(subparsers)
    _build_serve_api_parser(subparsers)
    return parser


def main() -> None:
    parser = build_argument_parser()
    args = parser.parse_args()
    workflow = SproutWorkflow()
    project_store = SproutProjectStore()
    project_service = SproutProjectService()
    _configure_workflow_from_args(workflow, args)

    if args.command == "import-project":
        project_summary = project_service.import_project(
            project_root=args.project_root,
            import_mode=args.import_mode,
        )
        print("项目导入完成。")
        print(f"项目 ID：{project_summary['project_id']}")
        print(f"展示名称：{project_summary['display_name']}")
        print(f"项目目录：{project_summary['canonical_root']}")
        return

    if args.command == "list-projects":
        project_summaries = project_service.list_projects()
        print(f"项目数：{len(project_summaries)}")
        for project_summary in project_summaries:
            print(
                f"{project_summary['project_id']} | "
                f"{project_summary['display_name']} | "
                f"{project_summary['health_status']}"
            )
        return

    if args.command == "serve-api":
        run_sprout_api_server(host=args.host, port=args.port)
        return

    if args.command == "plan-topic":
        if not args.topic:
            parser.error("plan-topic 必须提供 --topic。")
        topic_input = _build_topic_input_from_args(args)
        project_bundle = workflow.plan_from_topic(
            topic_input=topic_input,
            output_root=args.output_root,
            project_name=args.project_name,
        )
        bundle_path = project_store.get_default_bundle_path(
            output_root=args.output_root,
            project_name=project_bundle.project_name,
        )
        print("Sprout 分镜规划完成。")
        print(f"项目名：{project_bundle.project_name}")
        print(f"标题：{project_bundle.episode.title}")
        print(f"Bundle：{bundle_path}")
        return

    if args.command == "plan-storyboard":
        topic_input = _build_topic_input_from_args(args)
        storyboard_text = Path(args.storyboard_file).expanduser().read_text(encoding="utf-8")
        project_bundle = workflow.plan_from_storyboard(
            storyboard_text=storyboard_text,
            output_root=args.output_root,
            topic_input=topic_input,
            project_name=args.project_name,
        )
        bundle_path = project_store.get_default_bundle_path(
            output_root=args.output_root,
            project_name=project_bundle.project_name,
        )
        print("Sprout 分镜整理完成。")
        print(f"项目名：{project_bundle.project_name}")
        print(f"标题：{project_bundle.episode.title}")
        print(f"Bundle：{bundle_path}")
        return

    bundle = project_store.load_bundle(args.bundle_file)
    output_root = _resolve_output_root(args, bundle)

    if args.command == "build-characters":
        workflow.build_characters(
            project_bundle=bundle,
            output_root=output_root,
            extra_reference_count=args.extra_reference_count,
            skip_existing=not args.force,
        )
        print("角色资产生成完成。")
        print(f"项目名：{bundle.project_name}")
        print(f"角色数：{len(bundle.characters)}")
        print(f"输出目录：{output_root}")
        return

    if args.command == "prepare-shots":
        workflow.prepare_shots(
            project_bundle=bundle,
            output_root=output_root,
            shot_ids=_parse_shot_ids(args.shot_ids),
        )
        print("镜头 prompt 准备完成。")
        print(f"项目名：{bundle.project_name}")
        print(f"输出目录：{output_root}")
        return

    if args.command == "generate-shots":
        workflow.generate_shots(
            project_bundle=bundle,
            output_root=output_root,
            shot_count=args.shot_count,
            shot_ids=_parse_shot_ids(args.shot_ids),
            skip_existing=not args.force,
        )
        print("镜头视频生成完成。")
        print(f"项目名：{bundle.project_name}")
        print(f"输出目录：{output_root}")
        return

    if args.command == "build-cards":
        workflow.build_workflow_cards(
            project_bundle=bundle,
            output_root=output_root,
        )
        print("即梦执行卡生成完成。")
        print(f"项目名：{bundle.project_name}")
        print(f"输出目录：{output_root}")
        return

    if args.command == "export":
        exported_paths = workflow.export_bundle(
            project_bundle=bundle,
            output_root=output_root,
        )
        print("项目导出完成。")
        for exported_path in sorted(exported_paths.values()):
            print(exported_path)
        return

    if args.command == "run-all":
        if not args.topic and not args.storyboard_file:
            parser.error("run-all 必须至少提供 --topic 或 --storyboard-file 之一。")
        topic_input = _build_topic_input_from_args(args)
        if args.storyboard_file:
            storyboard_text = Path(args.storyboard_file).expanduser().read_text(encoding="utf-8")
            project_bundle = workflow.run_from_storyboard(
                storyboard_text=storyboard_text,
                output_root=args.output_root,
                topic_input=topic_input,
                project_name=args.project_name,
                extra_reference_count=args.extra_reference_count,
                generate_video_shot_count=args.generate_video_shot_count,
            )
        else:
            project_bundle = workflow.run_from_topic(
                topic_input=topic_input,
                output_root=args.output_root,
                project_name=args.project_name,
                extra_reference_count=args.extra_reference_count,
                generate_video_shot_count=args.generate_video_shot_count,
            )
        print("Sprout 整体链路运行完成。")
        print(f"项目名：{project_bundle.project_name}")
        print(f"标题：{project_bundle.episode.title}")
        print(f"输出目录：{Path(args.output_root).expanduser()}")
        return

    parser.error(f"不支持的命令：{args.command}")


def _build_topic_input_from_args(args: argparse.Namespace) -> SproutTopicInput:
    return SproutTopicInput(
        topic=args.topic or "已有分镜整理",
        duration_seconds=args.duration_seconds,
        shot_count=args.shot_count,
        orientation=args.orientation,
        visual_style=args.visual_style,
        target_audience=getattr(args, "target_audience", None),
        notes=getattr(args, "notes", None),
    )


def _resolve_output_root(args: argparse.Namespace, bundle) -> Path:
    if getattr(args, "output_root", None):
        return Path(args.output_root).expanduser()
    if bundle.manifest and bundle.manifest.output_root:
        return Path(bundle.manifest.output_root).expanduser()
    return Path(args.bundle_file).expanduser().parent.parent


def _parse_shot_ids(value: str | None) -> list[str] | None:
    if not value:
        return None
    shot_ids = [item.strip() for item in value.split(",") if item.strip()]
    return shot_ids or None


def _parse_csv_items(value: str | None) -> list[str] | None:
    if not value:
        return None
    items = [item.strip() for item in value.split(",") if item.strip()]
    return items or None


def _configure_workflow_from_args(workflow: SproutWorkflow, args: argparse.Namespace) -> None:
    workflow.configure_video_model_preferences(
        single_reference_model_name=getattr(args, "single_reference_video_model", None),
        multi_reference_model_name=getattr(args, "multi_reference_video_model", None),
        fallback_multi_reference_model_names=_parse_csv_items(
            getattr(args, "fallback_multi_reference_video_models", None)
        ),
    )


def _add_topic_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--topic", help="一句题材输入")
    parser.add_argument("--project-name", help="项目名")
    parser.add_argument("--output-root", required=True, help="输出目录")
    parser.add_argument("--duration-seconds", type=int, default=60, help="总时长，默认 60")
    parser.add_argument("--shot-count", type=int, default=10, help="镜头数，默认 10")
    parser.add_argument("--orientation", default="9:16", help="画幅，默认 9:16")
    parser.add_argument("--visual-style", help="视觉风格")
    parser.add_argument("--target-audience", help="目标受众")
    parser.add_argument("--notes", help="补充说明")


def _add_bundle_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--bundle-file", required=True, help="bundle JSON 文件路径")
    parser.add_argument("--output-root", help="输出目录，默认优先读取 bundle 中的 output_root")


def _build_plan_topic_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("plan-topic", help="一句题材生成结构化分镜")
    _add_topic_common_arguments(parser)


def _build_plan_storyboard_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("plan-storyboard", help="已有分镜整理为结构化项目包")
    _add_topic_common_arguments(parser)
    parser.add_argument("--storyboard-file", required=True, help="已有分镜脚本文件路径")


def _build_build_characters_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("build-characters", help="生成人设图")
    _add_bundle_common_arguments(parser)
    parser.add_argument("--extra-reference-count", type=int, default=0, help="每个角色额外补图数量")
    parser.add_argument("--force", action="store_true", help="强制重跑，忽略已有角色图")


def _build_prepare_shots_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("prepare-shots", help="准备镜头 prompt 和绑定信息")
    _add_bundle_common_arguments(parser)
    parser.add_argument("--shot-ids", help="仅处理指定镜头 ID，多个用逗号分隔")


def _build_generate_shots_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("generate-shots", help="生成镜头视频")
    _add_bundle_common_arguments(parser)
    parser.add_argument("--shot-count", type=int, default=1, help="默认按顺序生成前 N 个镜头")
    parser.add_argument("--shot-ids", help="仅生成指定镜头 ID，多个用逗号分隔")
    parser.add_argument("--force", action="store_true", help="强制重跑，忽略已有镜头结果")
    parser.add_argument("--single-reference-video-model", help="单图图生视频模型名")
    parser.add_argument("--multi-reference-video-model", help="多参考图视频优先模型名")
    parser.add_argument("--fallback-multi-reference-video-models", help="多参考图回退模型列表，多个用逗号分隔")


def _build_build_cards_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("build-cards", help="生成即梦执行卡")
    _add_bundle_common_arguments(parser)


def _build_export_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("export", help="导出项目清单与执行卡")
    _add_bundle_common_arguments(parser)


def _build_run_all_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("run-all", help="运行完整链路")
    _add_topic_common_arguments(parser)
    parser.add_argument("--storyboard-file", help="已有分镜脚本文件路径")
    parser.add_argument("--extra-reference-count", type=int, default=0, help="每个角色额外补图数量")
    parser.add_argument("--generate-video-shot-count", type=int, default=1, help="实际生成视频的镜头数")
    parser.add_argument("--single-reference-video-model", help="单图图生视频模型名")
    parser.add_argument("--multi-reference-video-model", help="多参考图视频优先模型名")
    parser.add_argument("--fallback-multi-reference-video-models", help="多参考图回退模型列表，多个用逗号分隔")


def _build_import_project_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("import-project", help="导入已有 sprout 项目目录")
    parser.add_argument("--project-root", required=True, help="待导入项目目录")
    parser.add_argument(
        "--import-mode",
        default="reference",
        choices=["reference", "copy"],
        help="导入模式：reference 或 copy",
    )


def _build_list_projects_parser(subparsers: argparse._SubParsersAction) -> None:
    subparsers.add_parser("list-projects", help="查看已导入项目")


def _build_serve_api_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("serve-api", help="启动一期后端 API 服务")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址")
    parser.add_argument("--port", type=int, default=8765, help="监听端口")


if __name__ == "__main__":
    main()
