from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
import time
from pathlib import Path

from app.services.platform_support import resolve_argv, split_command
from app.services.project_discovery import default_scan_roots, discover_projects
from app.services.task_status import format_task_status, normalize_status
from app.storage.database import TaskDatabase
from app.ai.ai_router import AIRouter, RouterPolicy
from app.ai.base_provider import TaskRequest, ExecutionResult
from app.ai.provider_registry import ProviderRegistry
from app.ai.providers.antigravity_provider import AntigravityProvider
from app.ai.providers.claude_provider import ClaudeProvider
from app.ai.providers.codex_provider import CodexProvider
from app.ai.providers.muse_provider import MuseProvider

log = logging.getLogger(__name__)


def _parse_task_request(request_text: str) -> tuple[str, str, str, str]:
    match = re.match(r"^\[Project: (.*?) \| Path: (.*?)\]\n(.*)$", request_text, re.S)
    if not match:
        raise ValueError("Task không có metadata dự án hợp lệ; từ chối chạy.")
    project_name, raw_path, payload = match.groups()
    mode = "EXECUTE"
    mode_match = re.match(r"^\[Mode: (ANALYSIS|EXECUTE)\]\n", payload)
    if mode_match:
        mode = mode_match.group(1)
        payload = payload[mode_match.end():]
    else:
        # Backward compatibility for tasks created before prompt modes were stored.
        normalized = payload.casefold()
        read_markers = ("đọc dự án", "đọc hiểu", "phân tích codebase", "lập bản đồ", "index codebase", "analyze codebase", "understand the project")
        edit_markers = ("sửa", "fix", "implement", "thêm", "triển khai", "refactor", "viết code", "tạo chức năng")
        if any(term in normalized for term in read_markers) and not any(term in normalized for term in edit_markers):
            mode = "ANALYSIS"
    return project_name, raw_path, mode, payload.strip()


def _load_prompt(filename: str) -> str:
    prompt_path = Path(__file__).resolve().parents[1] / "prompts" / filename
    try:
        return prompt_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"Không đọc được prompt mặc định {prompt_path}: {exc}") from exc


def _agent_prompt(mode: str, project_name: str, project_path: Path, user_request: str) -> str:
    context = (
        f"\n\nDỰ ÁN ĐƯỢC CHỌN: {project_name}\n"
        f"ĐƯỜNG DẪN: {project_path}\n"
        f"YÊU CẦU NGUYÊN BẢN CỦA NGƯỜI DÙNG:\n{user_request}\n"
    )
    if mode == "ANALYSIS":
        return (
            _load_prompt("01_project_analysis.md") + context +
            "\nRÀNG BUỘC BỔ SUNG: Chỉ đọc và báo cáo qua output của CLI. Không tạo báo cáo thành file, "
            "không sửa/tạo/xóa/di chuyển file, không thay đổi cấu hình/database/dependency. "
            "Không đọc .env hoặc file chứa credentials/secrets. Trả về báo cáo Markdown và Mermaid trực tiếp trong output."
        )
    return _load_prompt("02_task_execution.md") + context + "\nHãy thực hiện task theo đúng phạm vi đã nêu."


def _is_allowed_project(project_path: Path) -> bool:
    try:
        resolved = project_path.expanduser().resolve(strict=True)
        if not resolved.is_dir():
            return False
        for root in default_scan_roots():
            try:
                resolved.relative_to(root.resolve(strict=True))
                return True
            except (ValueError, OSError):
                continue
    except OSError:
        return False
    return False


_WATCH_SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "build", "dist", ".dart_tool", "__pycache__", ".next", ".idea"}


def _snapshot_project_files(root: Path, max_files: int = 20000) -> dict[str, tuple[int, int]]:
    """Return a bounded snapshot of ordinary project files for best-effort activity reporting."""
    snapshot: dict[str, tuple[int, int]] = {}
    count = 0
    for current, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in _WATCH_SKIP_DIRS and not d.startswith(".")]
        for filename in files:
            if filename in {".DS_Store"} or filename.endswith((".pyc", ".log", ".sqlite3-wal", ".sqlite3-shm")):
                continue
            path = Path(current) / filename
            try:
                stat = path.stat(follow_symlinks=False)
                if not path.is_file():
                    continue
                rel = path.relative_to(root).as_posix()
                snapshot[rel] = (stat.st_mtime_ns, stat.st_size)
                count += 1
                if count >= max_files:
                    return snapshot
            except OSError:
                continue
    return snapshot


def _changed_file_events(before: dict[str, tuple[int, int]], after: dict[str, tuple[int, int]]) -> list[str]:
    events: list[str] = []
    for path in sorted(after):
        if path not in before:
            events.append(f"📄 Phát hiện file mới: {path}")
        elif after[path] != before[path]:
            events.append(f"📝 Phát hiện file thay đổi: {path}")
    for path in sorted(before.keys() - after.keys()):
        events.append(f"🗑️ Phát hiện file đã biến mất: {path}")
    return events[-30:]


async def _run_process(
    args: list[str], cwd: Path, timeout: int, on_progress=None
) -> tuple[int, str]:
    """Run a subprocess while consuming stdout continuously (not only at exit)."""
    # resolve_argv: trên Windows tìm npm.cmd / go.exe thay vì phụ thuộc shell.
    cmd = resolve_argv(args)
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    chunks: list[str] = []
    last_update = 0.0
    loop = asyncio.get_running_loop()
    baseline = await asyncio.to_thread(_snapshot_project_files, cwd)
    last_snapshot = baseline
    activity_events: list[str] = []
    last_scan = loop.time()
    try:
        async def consume_output():
            nonlocal last_update, last_snapshot, last_scan
            while True:
                try:
                    raw = await asyncio.wait_for(proc.stdout.readline(), timeout=2.0)
                except asyncio.TimeoutError:
                    raw = None
                now = loop.time()
                if raw == b"":
                    break
                if raw:
                    line = raw.decode(errors="replace")
                    chunks.append(line)
                    # Preserve actual CLI output; never claim an inferred file is being edited.
                    if on_progress:
                        activity_events.append(line.rstrip())
                        activity_events[:] = activity_events[-12:]

                if now - last_scan >= 3.0:
                    current_snapshot = await asyncio.to_thread(_snapshot_project_files, cwd)
                    changes = _changed_file_events(last_snapshot, current_snapshot)
                    if changes:
                        activity_events.extend(changes)
                        activity_events[:] = activity_events[-12:]
                    last_snapshot = current_snapshot
                    last_scan = now

                current = ''.join(chunks)[-1800:]
                if activity_events:
                    current = (current + "\n\nHOẠT ĐỘNG FILE (phát hiện bằng cách so sánh snapshot; không khẳng định file đang được mở):\n" + "\n".join(activity_events))[-2600:]
                urgent = bool(raw) and any(word in line.lower() for word in ("error", "denied", "permission", "failed", "exception"))
                if on_progress and (now - last_update >= 5 or urgent or (changes if 'changes' in locals() else [])):
                    try:
                        await on_progress(current or "Antigravity đang chạy; chưa xuất log mới.")
                    except Exception:
                        log.exception("Could not send live task log to Telegram")
                    last_update = now
        await asyncio.wait_for(consume_output(), timeout=timeout)
        await asyncio.wait_for(proc.wait(), timeout=10)
        final_snapshot = await asyncio.to_thread(_snapshot_project_files, cwd)
        final_changes = _changed_file_events(baseline, final_snapshot)
        if final_changes:
            chunks.append("\n[FILE ACTIVITY SUMMARY]\n" + "\n".join(final_changes))
    except asyncio.TimeoutError:
        proc.kill()
        try:
            await proc.wait()
        except Exception:
            pass
        output = ''.join(chunks)[-3000:]
        raise TimeoutError(f"Lệnh quá thời gian {timeout} giây.\n{output}")
    return proc.returncode or 0, ''.join(chunks)[-10000:]


async def _run_tests(project_path: Path, timeout: int) -> str:
    # sys.executable: dùng đúng Python đang chạy bot (ổn định hơn "python" trên Windows).
    if (project_path / "pyproject.toml").exists() or (project_path / "pytest.ini").exists():
        args = [sys.executable, "-m", "pytest", "-q"]
    elif (project_path / "package.json").exists():
        try:
            package = json.loads((project_path / "package.json").read_text(encoding="utf-8"))
            scripts = package.get("scripts", {})
        except Exception:
            return "Không chạy test: không đọc được package.json."
        if "test" not in scripts:
            return "Không tìm thấy script test trong package.json; bỏ qua test."
        # Use the project's declared npm test script without injecting runner-specific flags.
        args = ["npm", "test"]
    elif (project_path / "go.mod").exists():
        args = ["go", "test", "./..."]
    else:
        return "Không nhận diện được lệnh test an toàn; đã bỏ qua kiểm thử tự động."
    try:
        code, output = await _run_process(args, project_path, timeout)
        return f"Lệnh test: {' '.join(args)}\nExit code: {code}\n{output[-5000:]}"
    except FileNotFoundError as exc:
        return f"Không chạy được test vì thiếu lệnh {exc.filename}."
    except TimeoutError as exc:
        return str(exc)


def _is_blocked_output(text: str) -> bool:
    lowered = text.casefold()
    return any(
        marker in lowered
        for marker in (
            "auto-denied",
            "cannot prompt for",
            "permission that headless mode",
            "blocked",
            "access denied",
            "permission denied",
        )
    )


def _decide_execute_status(
    code: int, agent_output: str, test_report: str, audit_report: str
) -> str:
    """Quyết định trạng thái cuối — không COMPLETED chỉ vì exit code 0."""
    if _is_blocked_output(agent_output) and (
        code != 0 or "không hoàn thành" in agent_output.casefold()
    ):
        return "BLOCKED"
    if code != 0:
        return "FAILED"
    if len(agent_output.strip()) < 20:
        return "FAILED"
    combined = f"{audit_report}\n{test_report}".casefold()
    warning_markers = (
        "không xác minh được",
        "not run",
        "not verified",
        "pass with warnings",
        "trạng thái audit: fail",
        "audit status: fail",
        "p0",
        "p1",
        "exit code: 1",
        "exit code: 2",
        "không tìm thấy script test",
        "không nhận diện được lệnh test",
        "không chạy audit vì bước triển khai không thành công",
    )
    if not audit_report.strip() or any(marker in combined for marker in warning_markers):
        return "PARTIAL"
    if "blocked" in combined:
        return "BLOCKED"
    return "COMPLETED"


def init_ai_router(settings) -> AIRouter:
    registry = ProviderRegistry()
    registry.register(AntigravityProvider(agy_command=getattr(settings, "agy_command", None)))
    registry.register(CodexProvider(api_key=getattr(settings, "openai_api_key", "")))
    registry.register(ClaudeProvider(api_key=getattr(settings, "anthropic_api_key", "")))
    registry.register(MuseProvider(api_key=getattr(settings, "muse_api_key", "")))
    try:
        policy = RouterPolicy(getattr(settings, "ai_router_policy", "balanced"))
    except (ValueError, TypeError):
        policy = RouterPolicy.BALANCED
    return AIRouter(
        registry=registry,
        policy=policy,
        fallback_enabled=getattr(settings, "ai_fallback_enabled", True),
    )


async def process_one(application, task: dict) -> None:
    db: TaskDatabase = application.bot_data["database"]
    settings = application.bot_data["settings"]
    task_id = int(task["id"])
    user_id = int(task["telegram_user_id"])
    progress_message = None

    def set_step(step: str, event_type: str = "", details: str = "") -> None:
        try:
            db.update_task_progress(task_id, step, event_type, details)
        except Exception:
            log.exception("Could not update progress for task %s", task_id)

    def record_event(event_type: str, details: str = "") -> None:
        try:
            db.add_task_event(task_id, event_type, details)
        except Exception:
            log.exception("Could not record event %s for task %s", event_type, task_id)

    set_step("Worker started", "WORKER_STARTED", "Worker đã nhận task và bắt đầu xử lý.")
    try:
        project_name, raw_path, mode, user_request = _parse_task_request(task["request_text"])
        project_path = Path(raw_path)
        if not _is_allowed_project(project_path):
            raise PermissionError("Dự án không nằm trong thư mục được phép quét hoặc không còn tồn tại.")
        resolved = project_path.resolve(strict=True)
        projects = discover_projects()
        if not any(Path(p["path"]).resolve() == resolved for p in projects):
            raise PermissionError("Dự án không còn nằm trong danh sách phát hiện hợp lệ.")

        mode_label = "ĐỌC HIỂU DỰ ÁN · CHỈ ĐỌC" if mode == "ANALYSIS" else "TRIỂN KHAI TASK"

        router: AIRouter = application.bot_data.setdefault("ai_router", init_ai_router(settings))
        command = split_command(settings.agy_command)
        if not command:
            raise RuntimeError("AGY_COMMAND đang để trống.")
        prompt = _agent_prompt(mode, project_name, resolved, user_request)

        task_req = TaskRequest(
            task_id=task_id,
            mode=mode,
            project_name=project_name,
            project_path=resolved,
            user_request=user_request,
            prompt=prompt,
            timeout_seconds=settings.agent_timeout_seconds,
        )
        decision = router.route_task(task_req)
        if not decision.selected_provider:
            reasons = "; ".join(f"{k}: {v}" for k, v in decision.rejections.items())
            raise RuntimeError(f"Không có AI provider nào khả dụng ({reasons})")

        selected_provider = decision.selected_provider
        record_event(
            "AI_ROUTED",
            f"AI Router đã chọn {selected_provider.name} "
            f"(score: {decision.score:.1f}, p50 latency: {selected_provider.metrics.median_latency():.2f}s, "
            f"thời gian routing: {decision.decision_latency_ms:.2f}ms)"
        )

        # Reuse the QUEUED confirmation message so it cannot remain stale.
        status_chat_id = task.get("status_chat_id")
        status_message_id = task.get("status_message_id")
        initial_text = (
            f"🚀 TASK-{task_id:04d} — RUNNING\n"
            f"AI: {selected_provider.name} | Giai đoạn: Khởi chạy\n"
            f"Dự án: {project_name}\nChế độ: {mode_label}\n\n"
            "📡 Đang thu thập log thực tế; phát hiện file chỉ phản ánh thay đổi snapshot."
        )
        if status_chat_id and status_message_id:
            try:
                progress_message = await application.bot.edit_message_text(
                    chat_id=int(status_chat_id),
                    message_id=int(status_message_id),
                    text=initial_text,
                )
            except Exception as exc:
                log.warning("Cannot edit queued message for task %s: %s", task_id, exc)
        if progress_message is None:
            progress_message = await application.bot.send_message(user_id, initial_text)
        last_progress_text = ""
        last_event_at = 0.0

        async def report_live_log(tail: str) -> None:
            nonlocal last_progress_text, last_event_at
            body = f"🔵 TASK-{task_id:04d} — {mode_label} ({selected_provider.name})\nDự án: {project_name}\n\n{tail[-2800:]}"
            now = time.monotonic()
            if now - last_event_at >= 15:
                record_event("PROGRESS", tail[-2500:])
                last_event_at = now
            if body == last_progress_text:
                return
            try:
                await progress_message.edit_text(body[-3900:])
                last_progress_text = body
            except Exception as exc:
                if "message is not modified" not in str(exc).lower():
                    log.warning("Cannot update live log for task %s: %s", task_id, exc)

        if mode == "ANALYSIS":
            set_step("Project analysis", "ANALYSIS_STARTED", f"Bắt đầu phân tích dự án bằng {selected_provider.name} (chỉ đọc).")
            set_step("Project analysis", "EXECUTION_SKIPPED", "Chế độ ANALYSIS — bỏ qua task execution.")
            set_step("Project analysis", "TESTING_SKIPPED", "Chế độ ANALYSIS — bỏ qua kiểm thử tự động.")
            set_step("Project analysis", "AUDIT_SKIPPED", "Chế độ ANALYSIS — bỏ qua post-task audit agent.")
        else:
            set_step("Task execution", "ANALYSIS_SKIPPED", "Chế độ EXECUTE — phân tích nằm trong bước triển khai.")
            set_step("Task execution", "EXECUTION_STARTED", f"Bắt đầu triển khai task bằng {selected_provider.name}.")

        if selected_provider.name == "Antigravity":
            code, agent_output = await _run_process(
                command + ["-p", prompt], resolved, settings.agent_timeout_seconds,
                on_progress=report_live_log,
            )
        else:
            exec_res = await selected_provider.execute_task(task_req, on_progress=report_live_log)
            code, agent_output = exec_res.exit_code, exec_res.output

        # Safe fallback if primary provider failed and fallback enabled
        if code != 0 and router.fallback_enabled:
            fallback_decision = router.route_fallback(task_req, failed_providers={selected_provider.name})
            if fallback_decision and fallback_decision.selected_provider:
                fallback_p = fallback_decision.selected_provider
                record_event("AI_FALLBACK", f"Chuyển sang AI dự phòng: {fallback_p.name}")
                await report_live_log(f"⚠️ {selected_provider.name} không hoàn tất. Thử lại với AI dự phòng {fallback_p.name}...")
                selected_provider = fallback_p
                if fallback_p.name == "Antigravity":
                    code, agent_output = await _run_process(
                        command + ["-p", prompt], resolved, settings.agent_timeout_seconds,
                        on_progress=report_live_log,
                    )
                else:
                    fb_res = await fallback_p.execute_task(task_req, on_progress=report_live_log)
                    code, agent_output = fb_res.exit_code, fb_res.output
        lowered_output = agent_output.casefold()
        denied_without_work = any(
            marker in lowered_output
            for marker in (
                "no output produced",
                "auto-denied",
                "cannot prompt for",
                "permission that headless mode",
            )
        )
        # Exit 0 alone is not success — require usable output and no hard denial.
        if code == 0 and denied_without_work:
            code = 1
            agent_output = (
                "Agent không hoàn thành yêu cầu do công cụ/quyền bị từ chối.\n\n" + agent_output
            )
        if code == 0 and len(agent_output.strip()) < 20:
            code = 1
            agent_output = (
                "Agent kết thúc nhưng không tạo báo cáo đủ nội dung; "
                "không thể xác nhận hoàn thành.\n\n" + agent_output
            )

        if mode == "ANALYSIS":
            if code == 0:
                set_step("Project analysis complete", "ANALYSIS_COMPLETED", agent_output[-2000:])
            elif _is_blocked_output(agent_output):
                set_step("Project analysis blocked", "ANALYSIS_BLOCKED", agent_output[-2000:])
            else:
                set_step("Project analysis failed", "ANALYSIS_FAILED", agent_output[-2000:])
        else:
            if code == 0:
                set_step("Task execution complete", "EXECUTION_COMPLETED", agent_output[-2000:])
            elif _is_blocked_output(agent_output):
                set_step("Task execution blocked", "EXECUTION_BLOCKED", agent_output[-2000:])
            else:
                set_step("Task execution failed", "EXECUTION_FAILED", agent_output[-2000:])

        test_report = "Không áp dụng: chế độ đọc hiểu chỉ đọc, không chạy test để tránh tác dụng phụ."
        audit_agent_report = ""
        local_audit_lines: list[str] = []

        if mode == "EXECUTE" and code == 0:
            await report_live_log(
                "✅ Đã xong bước triển khai.\n"
                "🧪 GIAI ĐOẠN: Đang chạy kiểm thử..."
            )
            set_step("Tests and validation", "TESTING_STARTED", "Bắt đầu kiểm thử tự động.")
            test_report = await _run_tests(resolved, settings.test_timeout_seconds)
            test_failed = "exit code: 1" in test_report.casefold() or "exit code: 2" in test_report.casefold()
            set_step(
                "Tests finished",
                "TESTING_FAILED" if test_failed else "TESTING_FINISHED",
                test_report[-2500:],
            )

            await report_live_log(
                "✅ Đã hoàn tất bước triển khai.\n"
                "✅ Đã hoàn tất bước kiểm thử (xem báo cáo để biết kết quả).\n"
                "🔎 GIAI ĐOẠN: Bắt đầu POST-TASK AUDIT (chỉ đọc, không sửa code)..."
            )
            set_step("Post-task audit", "AUDIT_STARTED", "Bắt đầu POST-TASK AUDIT chỉ đọc.")
            audit_prompt = (
                _load_prompt("03_post_task_audit.md")
                + f"\n\nTASK ĐÃ YÊU CẦU:\n{user_request}\n"
                + f"\nDỰ ÁN: {project_name}\nĐƯỜNG DẪN: {resolved}\n"
                + "\nKẾT QUẢ AGENT TRƯỚC ĐÓ (chỉ là thông tin tham khảo, phải xác minh lại):\n"
                + f"{agent_output[-6000:]}\n"
                + f"\nKẾT QUẢ KIỂM THỬ ĐÃ CHẠY:\n{test_report[-4000:]}\n"
                + "\nChỉ audit và báo cáo. Tuyệt đối không sửa bất kỳ file nào."
            )
            audit_code, audit_agent_report = await _run_process(
                command + ["-p", audit_prompt],
                resolved,
                settings.agent_timeout_seconds,
                on_progress=lambda tail: report_live_log("POST-TASK AUDIT\n" + tail),
            )
            if audit_code != 0 or len(audit_agent_report.strip()) < 20:
                audit_agent_report = (
                    "POST-TASK AUDIT KHÔNG XÁC MINH ĐƯỢC: agent không trả về báo cáo audit hợp lệ. "
                    f"Exit code: {audit_code}.\n" + audit_agent_report
                )
                set_step("Post-task audit failed", "AUDIT_FAILED", audit_agent_report[-2500:])
            else:
                set_step("Post-task audit complete", "AUDIT_FINISHED", audit_agent_report[-2500:])
        elif mode == "EXECUTE":
            set_step("Tests skipped", "TESTING_SKIPPED", "Bỏ qua test vì bước triển khai không thành công.")
            set_step("Audit skipped", "AUDIT_SKIPPED", "Bỏ qua audit vì bước triển khai không thành công.")

        # Local read-only Git review after the agent pass. Do not stage/commit or mutate user changes.
        # Dùng shortstat + vài dòng status — tránh nhét cả diff --stat hàng trăm file vào Telegram/DB.
        if (resolved / ".git").exists():
            try:
                status_code, status_output = await _run_process(
                    ["git", "status", "--short", "--branch"], resolved, 60
                )
                diff_code, diff_output = await _run_process(["git", "diff", "--check"], resolved, 60)
                stat_code, stat_output = await _run_process(
                    ["git", "diff", "--shortstat"], resolved, 60
                )
                status_lines = (status_output or "").splitlines()
                status_preview = "\n".join(status_lines[:25])
                if len(status_lines) > 25:
                    status_preview += f"\n… +{len(status_lines) - 25} more paths"
                check_preview = (diff_output or "(không có lỗi whitespace)")[-800:]
                local_audit_lines.extend(
                    [
                        f"Git status --short --branch: exit {status_code}\n"
                        f"{status_preview or '(clean hoặc không có output)'}",
                        f"Git diff --check: exit {diff_code}\n{check_preview}",
                        f"Git diff --shortstat: exit {stat_code}\n"
                        f"{stat_output or '(không có thay đổi tracked trong diff; không đủ để kết luận task thành công)'}",
                    ]
                )
            except Exception as exc:
                local_audit_lines.append(f"Git audit không hoàn tất: {type(exc).__name__}: {exc}")
        else:
            local_audit_lines.append("Bỏ qua Git audit: thư mục này không có .git trực tiếp.")

        if mode == "ANALYSIS":
            report = (
                "CHẾ ĐỘ: READ-ONLY PROJECT ANALYSIS (PROMPT 1)\n"
                f"Antigravity exit code: {code}\n\nBÁO CÁO PHÂN TÍCH CODEBASE:\n{agent_output}\n\n"
                "KIỂM TRA KHÔNG GHI FILE:\n" + "\n".join(local_audit_lines)
            )
            if code == 0:
                final_status = "COMPLETED"
            elif _is_blocked_output(agent_output):
                final_status = "BLOCKED"
            else:
                final_status = "FAILED"
        else:
            report = (
                "CHẾ ĐỘ: TASK EXECUTION + POST-TASK AUDIT (PROMPT 2 + PROMPT 3)\n"
                f"Antigravity exit code: {code}\n\nKẾT QUẢ TRIỂN KHAI:\n{agent_output}\n\n"
                f"KIỂM THỬ:\n{test_report}\n\n"
                f"POST-TASK AUDIT (READ-ONLY):\n"
                f"{audit_agent_report or 'Không chạy audit vì bước triển khai không thành công.'}\n\n"
                "KIỂM TRA GIT CỤC BỘ:\n" + "\n".join(local_audit_lines)
            )
            final_status = _decide_execute_status(code, agent_output, test_report, audit_agent_report)

        # error_text ngắn gọn — không nhét cả report/git dump (Telegram /status sẽ đọc khó).
        if final_status == "COMPLETED":
            error_text = ""
        else:
            error_text = (
                f"Final status: {final_status}. "
                "Xem Tests / Post-task audit / Git shortstat trong báo cáo."
            )
        set_step("Final report delivery", "REPORT_STARTED", "Đang gửi báo cáo cuối lên Telegram.")
        db.finish_task(task_id, final_status, report, error_text, current_step="Final report delivery")
        finished = db.get_task(task_id) or task
        view = dict(finished)
        view["status"] = normalize_status(finished.get("status"))
        try:
            events = db.list_task_events(task_id, limit=80)
        except Exception:
            events = []
        final_text = format_task_status(view, events)
        try:
            await progress_message.edit_text(final_text[:3900])
            set_step("Finished", "REPORT_DELIVERED", "Đã gửi báo cáo Telegram thành công.")
        except Exception as exc:
            log.warning("Primary report edit failed for task %s: %s", task_id, exc)
            try:
                await application.bot.send_message(user_id, final_text[:3900])
                set_step("Finished", "REPORT_DELIVERED", "Đã gửi báo cáo Telegram bằng tin nhắn mới.")
            except Exception as send_exc:
                log.exception("Cannot notify task owner for task %s", task_id)
                set_step(
                    "Report delivery failed",
                    "REPORT_FAILED",
                    f"Telegram delivery failed: {type(send_exc).__name__}: {send_exc}",
                )
                # Công việc đã xong trong DB; chỉ ghi nhận lỗi gửi — không đổi COMPLETED → FAILED.
                if final_status == "COMPLETED":
                    db.finish_task(
                        task_id,
                        "PARTIAL",
                        report + f"\n\nTELEGRAM DELIVERY ERROR: {send_exc}",
                        f"Telegram delivery failed: {send_exc}",
                        current_step="Report delivery failed",
                    )
    except Exception as exc:
        log.exception("Task %s failed", task_id)
        report = f"Task thất bại: {type(exc).__name__}: {exc}"
        set_step("Failed", "FAILED", report)
        db.finish_task(task_id, "FAILED", report, report, current_step="Failed")
        try:
            if progress_message:
                await progress_message.edit_text(f"❌ TASK-{task_id:04d} FAILED\n{report[:3000]}")
            else:
                await application.bot.send_message(user_id, f"❌ TASK-{task_id:04d} FAILED\n{report[:3000]}")
            record_event("REPORT_DELIVERED", "Đã gửi thông báo FAILED.")
        except Exception:
            record_event("REPORT_FAILED", "Không gửi được thông báo FAILED lên Telegram.")
            log.exception("Cannot notify task owner for task %s", task_id)


async def worker_loop(application) -> None:
    db: TaskDatabase = application.bot_data["database"]
    settings = application.bot_data["settings"]
    # Worker restart: mọi RUNNING cũ là orphan — không để treo RUNNING vô hạn.
    orphaned = db.reclaim_orphaned_running_tasks(
        "Worker restarted while task was RUNNING; marked FAILED to avoid stale status."
    )
    if orphaned:
        log.warning("Reclaimed orphaned RUNNING tasks: %s", orphaned)
    log.info("Antigravity task worker started")
    idle_rounds = 0
    # Cho phép idle lâu hơn timeout agent một chút (PROGRESS vẫn cập nhật updated_at).
    stale_limit = max(300, int(settings.agent_timeout_seconds) + 120)
    while True:
        try:
            if not application.bot_data.get("agent_enabled", True):
                await asyncio.sleep(2)
                continue
            idle_rounds += 1
            if idle_rounds % 15 == 0:
                stale = db.fail_stale_running_tasks(stale_limit)
                if stale:
                    log.warning("Marked stale RUNNING tasks as FAILED: %s", stale)
            task = db.claim_next_task()
            if task:
                await process_one(application, task)
            else:
                await asyncio.sleep(2)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Worker loop error")
            await asyncio.sleep(3)
