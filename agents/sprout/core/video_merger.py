"""Sprout 视频合成器。"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import textwrap
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .utils import ensure_directory


@dataclass
class SproutVideoMerger:
    """合并多个镜头视频为最终成片。"""

    ffmpeg_binary: str | None = None
    swift_binary: str | None = None

    def build_merge_plan(self, input_paths: list[str | Path]) -> dict[str, object]:
        """统计片段分辨率并生成最终合成计划。"""

        resolved_input_paths = [Path(path).expanduser().resolve() for path in input_paths]
        if not resolved_input_paths:
            raise ValueError("没有可用于合并的视频片段。")
        for input_path in resolved_input_paths:
            if not input_path.exists():
                raise FileNotFoundError(f"待合并视频不存在：{input_path}")

        clip_profiles = self._inspect_video_profiles(resolved_input_paths)
        target_render_size = self._choose_target_render_size(clip_profiles)
        target_width = int(target_render_size["width"])
        target_height = int(target_render_size["height"])
        target_aspect_ratio = target_width / max(target_height, 1)

        resolution_counter = Counter(
            f"{profile['display_width']} x {profile['display_height']}"
            for profile in clip_profiles
        )
        orientation_counter = Counter(profile["orientation"] for profile in clip_profiles)
        segment_reports: list[dict[str, object]] = []
        upscale_segment_count = 0
        padded_segment_count = 0

        for index, profile in enumerate(clip_profiles, start=1):
            display_width = int(profile["display_width"])
            display_height = int(profile["display_height"])
            fit_scale = min(
                target_width / max(display_width, 1),
                target_height / max(display_height, 1),
            )
            if fit_scale > 1.001:
                scale_mode = "upscale_to_fit"
                upscale_segment_count += 1
            elif fit_scale < 0.999:
                scale_mode = "downscale_to_fit"
            else:
                scale_mode = "native"

            aspect_ratio = display_width / max(display_height, 1)
            needs_padding = abs(aspect_ratio - target_aspect_ratio) > 0.01
            if needs_padding:
                padded_segment_count += 1

            segment_reports.append(
                {
                    "index": index,
                    "shot_id": self._extract_shot_id(profile["file_name"]),
                    "file_name": profile["file_name"],
                    "duration_seconds": profile["duration_seconds"],
                    "display_width": display_width,
                    "display_height": display_height,
                    "resolution_label": f"{display_width} x {display_height}",
                    "orientation": profile["orientation"],
                    "scale_mode": scale_mode,
                    "needs_padding": needs_padding,
                }
            )

        warnings: list[str] = []
        if upscale_segment_count == 0:
            warnings.append("目标输出分辨率已优先选择无需放大低分辨率片段的方案。")
        else:
            warnings.append(
                f"有 {upscale_segment_count} 段片段需要放大适配，建议后续优先重生成低分辨率片段。"
            )
        if len(resolution_counter) > 1:
            warnings.append("检测到片段分辨率不一致，系统会以低分辨率兼容高分辨率。")
        if len(orientation_counter) > 1 or padded_segment_count > 0:
            warnings.append("检测到横竖屏或宽高比不一致，部分片段会做黑边居中适配。")

        return {
            "strategy": "先统计片段分辨率，再按无需放大低分辨率片段优先的原则选择输出分辨率。",
            "segment_count": len(segment_reports),
            "target_render_size": {
                "width": target_width,
                "height": target_height,
                "label": f"{target_width} x {target_height}",
            },
            "resolution_summary": [
                {
                    "label": label,
                    "count": count,
                }
                for label, count in sorted(
                    resolution_counter.items(),
                    key=lambda item: (-item[1], item[0]),
                )
            ],
            "orientation_summary": dict(sorted(orientation_counter.items())),
            "upscale_segment_count": upscale_segment_count,
            "padded_segment_count": padded_segment_count,
            "segments": segment_reports,
            "warnings": warnings,
        }

    def merge_videos(
        self,
        input_paths: list[str | Path],
        output_path: str | Path,
        *,
        merge_plan: dict[str, object] | None = None,
    ) -> Path:
        """合并输入视频并输出最终成片。"""

        resolved_input_paths = [Path(path).expanduser().resolve() for path in input_paths]
        if not resolved_input_paths:
            raise ValueError("没有可用于合并的视频片段。")
        for input_path in resolved_input_paths:
            if not input_path.exists():
                raise FileNotFoundError(f"待合并视频不存在：{input_path}")

        resolved_output_path = Path(output_path).expanduser().resolve()
        ensure_directory(resolved_output_path.parent)
        if resolved_output_path.exists():
            resolved_output_path.unlink()

        merge_plan = merge_plan or self.build_merge_plan(resolved_input_paths)
        target_render_size = merge_plan["target_render_size"]

        swift_binary = self.swift_binary or shutil.which("swift")
        if swift_binary:
            self._merge_with_swift(
                swift_binary,
                resolved_input_paths,
                resolved_output_path,
                target_width=int(target_render_size["width"]),
                target_height=int(target_render_size["height"]),
            )
            return resolved_output_path

        ffmpeg_binary = self.ffmpeg_binary or shutil.which("ffmpeg")
        if ffmpeg_binary:
            self._merge_with_ffmpeg(ffmpeg_binary, resolved_input_paths, resolved_output_path)
            return resolved_output_path

        raise RuntimeError("当前环境缺少可用的视频合并能力，请安装 ffmpeg 或使用 macOS 自带 Swift。")

    def _inspect_video_profiles(self, input_paths: list[Path]) -> list[dict[str, object]]:
        swift_binary = self.swift_binary or shutil.which("swift")
        if not swift_binary:
            raise RuntimeError("当前环境缺少 Swift，无法统计视频分辨率信息。")

        swift_script = textwrap.dedent(
            """
            import Foundation
            import AVFoundation
            import CoreGraphics

            var results: [[String: Any]] = []
            for inputPath in CommandLine.arguments.dropFirst() {
                let asset = AVURLAsset(url: URL(fileURLWithPath: inputPath))
                guard let track = asset.tracks(withMediaType: .video).first else {
                    continue
                }
                let naturalSize = track.naturalSize
                let preferredTransform = track.preferredTransform
                let transformedRect = CGRect(origin: .zero, size: naturalSize).applying(preferredTransform)
                let displayWidth = Int(abs(transformedRect.width).rounded())
                let displayHeight = Int(abs(transformedRect.height).rounded())
                let orientation: String
                if displayHeight > displayWidth {
                    orientation = "portrait"
                } else if displayWidth > displayHeight {
                    orientation = "landscape"
                } else {
                    orientation = "square"
                }
                results.append([
                    "input_path": inputPath,
                    "file_name": URL(fileURLWithPath: inputPath).lastPathComponent,
                    "natural_width": Int(naturalSize.width.rounded()),
                    "natural_height": Int(naturalSize.height.rounded()),
                    "display_width": displayWidth,
                    "display_height": displayHeight,
                    "duration_seconds": CMTimeGetSeconds(asset.duration),
                    "orientation": orientation,
                ])
            }

            let jsonData = try JSONSerialization.data(withJSONObject: results, options: [.prettyPrinted])
            FileHandle.standardOutput.write(jsonData)
            """
        ).strip()

        with tempfile.TemporaryDirectory(prefix="sprout_video_probe_") as temp_dir:
            script_path = Path(temp_dir) / "probe.swift"
            script_path.write_text(swift_script, encoding="utf-8")
            result = subprocess.run(
                [swift_binary, str(script_path), *[str(path) for path in input_paths]],
                check=False,
                capture_output=True,
                text=True,
            )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "视频分辨率统计失败。")

        payload = json.loads(result.stdout or "[]")
        if not isinstance(payload, list) or not payload:
            raise RuntimeError("未能读取任何视频片段的分辨率信息。")
        return [item for item in payload if isinstance(item, dict)]

    @staticmethod
    def _choose_target_render_size(clip_profiles: list[dict[str, object]]) -> dict[str, int]:
        unique_sizes = {
            (int(profile["display_width"]), int(profile["display_height"]))
            for profile in clip_profiles
        }
        ranked_candidates: list[tuple[tuple[float, ...], tuple[int, int]]] = []
        for candidate_width, candidate_height in unique_sizes:
            upscale_segment_count = 0
            total_upscale_ratio = 0.0
            exact_match_count = 0
            padding_segment_count = 0
            candidate_aspect_ratio = candidate_width / max(candidate_height, 1)

            for profile in clip_profiles:
                display_width = int(profile["display_width"])
                display_height = int(profile["display_height"])
                fit_scale = min(
                    candidate_width / max(display_width, 1),
                    candidate_height / max(display_height, 1),
                )
                if fit_scale > 1.001:
                    upscale_segment_count += 1
                    total_upscale_ratio += fit_scale - 1.0
                if display_width == candidate_width and display_height == candidate_height:
                    exact_match_count += 1
                aspect_ratio = display_width / max(display_height, 1)
                if abs(aspect_ratio - candidate_aspect_ratio) > 0.01:
                    padding_segment_count += 1

            ranked_candidates.append(
                (
                    (
                        upscale_segment_count,
                        round(total_upscale_ratio, 6),
                        -exact_match_count,
                        padding_segment_count,
                        candidate_width * candidate_height,
                        candidate_width,
                        candidate_height,
                    ),
                    (candidate_width, candidate_height),
                )
            )

        _, (target_width, target_height) = min(ranked_candidates, key=lambda item: item[0])
        return {"width": target_width, "height": target_height}

    @staticmethod
    def _extract_shot_id(file_name: str) -> str | None:
        path_stem = Path(file_name).stem
        if path_stem.startswith("shot_"):
            return "_".join(path_stem.split("_")[:2])
        return None

    @staticmethod
    def _merge_with_ffmpeg(
        ffmpeg_binary: str,
        input_paths: list[Path],
        output_path: Path,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="sprout_concat_") as temp_dir:
            concat_file = Path(temp_dir) / "concat.txt"
            concat_lines = []
            for path in input_paths:
                escaped_path = str(path).replace("'", "'\\''")
                concat_lines.append(f"file '{escaped_path}'\n")
            concat_file.write_text(
                "".join(concat_lines),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    ffmpeg_binary,
                    "-y",
                    "-f",
                    "concat",
                    "-safe",
                    "0",
                    "-i",
                    str(concat_file),
                    "-c:v",
                    "libx264",
                    "-c:a",
                    "aac",
                    "-movflags",
                    "+faststart",
                    str(output_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "ffmpeg 合并视频失败。")

    @staticmethod
    def _merge_with_swift(
        swift_binary: str,
        input_paths: list[Path],
        output_path: Path,
        *,
        target_width: int,
        target_height: int,
    ) -> None:
        swift_script = textwrap.dedent(
            """
            import Foundation
            import AVFoundation
            import CoreGraphics

            struct ClipContext {
                let asset: AVURLAsset
                let sourceVideoTrack: AVAssetTrack
                let displaySize: CGSize
            }

            func resolvedRenderSize(for track: AVAssetTrack) -> CGSize {
                let transformedRect = CGRect(origin: .zero, size: track.naturalSize)
                    .applying(track.preferredTransform)
                return CGSize(width: abs(transformedRect.width), height: abs(transformedRect.height))
            }

            let arguments = CommandLine.arguments
            if arguments.count < 5 {
                fputs("参数不足。\\n", stderr)
                exit(2)
            }

            let targetWidth = Int(arguments[1]) ?? 720
            let targetHeight = Int(arguments[2]) ?? 1280
            let inputPaths = Array(arguments.dropFirst(3).dropLast())
            let outputPath = String(arguments.last!)
            let outputURL = URL(fileURLWithPath: outputPath)
            let fileManager = FileManager.default
            if fileManager.fileExists(atPath: outputURL.path) {
                try? fileManager.removeItem(at: outputURL)
            }

            let composition = AVMutableComposition()
            guard let compositionVideoTrack = composition.addMutableTrack(
                withMediaType: .video,
                preferredTrackID: kCMPersistentTrackID_Invalid
            ) else {
                fputs("无法创建视频轨道。\\n", stderr)
                exit(3)
            }
            let compositionAudioTrack = composition.addMutableTrack(
                withMediaType: .audio,
                preferredTrackID: kCMPersistentTrackID_Invalid
            )

            var clips: [ClipContext] = []
            for inputPath in inputPaths {
                let asset = AVURLAsset(url: URL(fileURLWithPath: inputPath))
                guard let sourceVideoTrack = asset.tracks(withMediaType: .video).first else {
                    fputs("存在没有视频轨道的文件：\\(inputPath)\\n", stderr)
                    exit(4)
                }
                clips.append(
                    ClipContext(
                        asset: asset,
                        sourceVideoTrack: sourceVideoTrack,
                        displaySize: resolvedRenderSize(for: sourceVideoTrack)
                    )
                )
            }

            var instructions: [AVMutableVideoCompositionInstruction] = []
            var currentTime = CMTime.zero
            let renderSize = CGSize(width: targetWidth, height: targetHeight)

            for clip in clips {
                let asset = clip.asset
                let sourceVideoTrack = clip.sourceVideoTrack
                let timeRange = CMTimeRange(start: .zero, duration: asset.duration)
                do {
                    try compositionVideoTrack.insertTimeRange(timeRange, of: sourceVideoTrack, at: currentTime)
                    if let sourceAudioTrack = asset.tracks(withMediaType: .audio).first,
                       let compositionAudioTrack {
                        try compositionAudioTrack.insertTimeRange(timeRange, of: sourceAudioTrack, at: currentTime)
                    }
                } catch {
                    fputs("插入轨道失败：\\(error.localizedDescription)\\n", stderr)
                    exit(5)
                }

                let instruction = AVMutableVideoCompositionInstruction()
                instruction.timeRange = CMTimeRange(start: currentTime, duration: asset.duration)
                let layerInstruction = AVMutableVideoCompositionLayerInstruction(assetTrack: compositionVideoTrack)

                let displaySize = clip.displaySize
                let scale = min(
                    renderSize.width / max(displaySize.width, 1),
                    renderSize.height / max(displaySize.height, 1)
                )
                var transform = sourceVideoTrack.preferredTransform.concatenating(
                    CGAffineTransform(scaleX: scale, y: scale)
                )
                let scaledRect = CGRect(origin: .zero, size: sourceVideoTrack.naturalSize).applying(transform)
                let translatedX = (renderSize.width - abs(scaledRect.width)) / 2.0 - scaledRect.origin.x
                let translatedY = (renderSize.height - abs(scaledRect.height)) / 2.0 - scaledRect.origin.y
                transform = transform.concatenating(
                    CGAffineTransform(translationX: translatedX, y: translatedY)
                )

                layerInstruction.setTransform(transform, at: currentTime)
                instruction.layerInstructions = [layerInstruction]
                instructions.append(instruction)
                currentTime = CMTimeAdd(currentTime, asset.duration)
            }

            guard let exportSession = AVAssetExportSession(
                asset: composition,
                presetName: AVAssetExportPresetHighestQuality
            ) else {
                fputs("无法创建导出任务。\\n", stderr)
                exit(6)
            }

            let videoComposition = AVMutableVideoComposition()
            videoComposition.instructions = instructions
            videoComposition.frameDuration = CMTime(value: 1, timescale: 30)
            videoComposition.renderSize = renderSize

            exportSession.outputURL = outputURL
            exportSession.outputFileType = .mp4
            exportSession.shouldOptimizeForNetworkUse = true
            exportSession.videoComposition = videoComposition

            let semaphore = DispatchSemaphore(value: 0)
            exportSession.exportAsynchronously {
                semaphore.signal()
            }
            semaphore.wait()

            if exportSession.status != .completed {
                let errorMessage = exportSession.error?.localizedDescription ?? "未知错误"
                fputs("导出最终成片失败：\\(errorMessage)\\n", stderr)
                exit(7)
            }
            """
        ).strip()

        with tempfile.TemporaryDirectory(prefix="sprout_swift_merge_") as temp_dir:
            script_path = Path(temp_dir) / "merge.swift"
            script_path.write_text(swift_script, encoding="utf-8")
            result = subprocess.run(
                [
                    swift_binary,
                    str(script_path),
                    str(target_width),
                    str(target_height),
                    *[str(path) for path in input_paths],
                    str(output_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "Swift 合并视频失败。")
