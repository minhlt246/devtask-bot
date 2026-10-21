"""Định dạng /status từ dữ liệu SQLite thật — không suy đoán tiến độ giả."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

# Trạng thái tổng được hỗ trợ (kèm alias legacy để hiển thị đúng dữ liệu cũ).
DISPLAY_STATUS = {
    "QUEUED": "QUEUED",
    "RUNNING": "RUNNING",
    "COMPLETED": "COMPLETED",
    "SUCCEEDED": "COMPLETED",
    "FAILED": "FAILED",
    "PARTIAL": "PARTIAL",
    "COMPLETED_WITH_WARNINGS": "PARTIAL",
    "BLOCKED": "BLOCKED",
    "CANCELLED": "CANCELLED",
}

STATUS_ICON = {
    "QUEUED": "🟡",
    "RUNNING": "🔵",
    "COMPLETED": "🟢",
    "FAILED": "🔴",
    "PARTIAL": "🟠",
    "BLOCKED": "⚪",
    "CANCELLED": "⚫",
}

PHASE_DEFS = (
    ("project_analysis", "Project analysis"),
    ("task_execution", "Task execution"),
    ("tests_and_validation", "Tests and validation"),
    ("post_task_audit", "Post-task audit"),
    ("final_report_delivery", "Final report delivery"),
)

# event_type → (phase_key, phase_state)
PHASE_EVENTS: dict[str, tuple[str, str]] = {
    "ANALYSIS_STARTED": ("project_analysis", "RUNNING"),
    "ANALYSIS_COMPLETED": ("project_analysis", "COMPLETED"),
    "ANALYSIS_FAILED": ("project_analysis", "FAILED"),
    "ANALYSIS_SKIPPED": ("project_analysis", "SKIPPED"),
    "ANALYSIS_BLOCKED": ("project_analysis", "BLOCKED"),
    "EXECUTION_STARTED": ("task_execution", "RUNNING"),
    "EXECUTION_COMPLETED": ("task_execution", "COMPLETED"),
    "EXECUTION_FAILED": ("task_execution", "FAILED"),
    "EXECUTION_SKIPPED": ("task_execution", "SKIPPED"),
    "EXECUTION_BLOCKED": ("task_execution", "BLOCKED"),
    "TESTING_STARTED": ("tests_and_validation", "RUNNING"),
    "TESTING": ("tests_and_validation", "RUNNING"),
    "TESTING_FINISHED": ("tests_and_validation", "COMPLETED"),
    "TESTING_FAILED": ("tests_and_validation", "FAILED"),
    "TESTING_SKIPPED": ("tests_and_validation", "SKIPPED"),
    "AUDIT_STARTED": ("post_task_audit", "RUNNING"),
    "AUDITING": ("post_task_audit", "RUNNING"),
    "AUDIT_FINISHED": ("post_task_audit", "COMPLETED"),
    "AUDIT_FAILED": ("post_task_audit", "FAILED"),
    "AUDIT_SKIPPED": ("post_task_audit", "SKIPPED"),
    "REPORT_STARTED": ("final_report_delivery", "RUNNING"),
    "REPORT_DELIVERED": ("final_report_delivery", "COMPLETED"),
    "REPORT_FINISHED": ("final_report_delivery", "COMPLETED"),
    "REPORT_FAILED": ("final_report_delivery", "FAILED"),
}

_TASK_ID_RE = re.compile(r"^(?:TASK-)?(\d+)$", re.IGNORECASE)
_GIT_SHORTSTAT_RE = re.compile(
    r"\d+ files? changed(?:, \d+ insertions?\(\+\))?(?:, \d+ deletions?\(-\))?"
)
_GIT_STAT_LINE_RE = re.compile(r"\|\s*\d+\s*[+-]+\s*$")
_NA = "Not available"
_NR = "Not recorded"


def parse_task_id(raw: str) -> int | None:
    """Nhận '14' hoặc 'TASK-0014' → int; không hợp lệ → None."""
    match = _TASK_ID_RE.match((raw or "").strip())
    if not match:
        return None
    return int(match.group(1))


def normalize_status(raw: str | None) -> str:
    key = (raw or "").strip().upper()
    return DISPLAY_STATUS.get(key, key or "UNKNOWN")


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _fmt_time(value: str | None) -> str:
    return value if value else _NR


def _fmt_duration(started: str | None, finished: str | None, status: str) -> str:
    start = _parse_iso(started)
    if not start:
        return _NR
    end = _parse_iso(finished)
    if not end:
        if status == "RUNNING":
            end = datetime.now(timezone.utc)
        else:
            return _NR
    seconds = max(0, int((end - start).total_seconds()))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h {minutes}m {secs}s"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def _project_label(task: dict[str, Any]) -> str:
    request = task.get("request_text") or ""
    match = re.match(r"^\[Project: (.*?) \| Path:", request)
    if match:
        return match.group(1).strip()
    return task.get("project_key") or _NA


def _latest_event_time(events: list[dict[str, Any]]) -> str | None:
    if not events:
        return None
    return events[-1].get("created_at")


def derive_phase_states(
    task: dict[str, Any], events: list[dict[str, Any]]
) -> dict[str, str]:
    """Suy ra trạng thái từng giai đoạn chỉ từ event/status đã lưu — không bịa."""
    states = {key: "PENDING" for key, _ in PHASE_DEFS}
    overall = normalize_status(task.get("status"))

    for event in events:
        mapped = PHASE_EVENTS.get((event.get("event_type") or "").upper())
        if not mapped:
            continue
        phase, state = mapped
        states[phase] = state

    # Task còn QUEUED: mọi giai đoạn PENDING.
    if overall == "QUEUED":
        return {key: "PENDING" for key, _ in PHASE_DEFS}

    # Không có event phase chi tiết — chỉ suy ở mức tối thiểu từ status tổng.
    has_phase_events = any(
        (e.get("event_type") or "").upper() in PHASE_EVENTS for e in events
    )
    if not has_phase_events:
        if overall == "RUNNING":
            step = (task.get("current_step") or "").casefold()
            if "test" in step:
                states["task_execution"] = "COMPLETED"
                states["tests_and_validation"] = "RUNNING"
            elif "audit" in step:
                states["task_execution"] = "COMPLETED"
                states["tests_and_validation"] = "COMPLETED"
                states["post_task_audit"] = "RUNNING"
            elif "report" in step:
                states["final_report_delivery"] = "RUNNING"
            else:
                # Không chắc giai đoạn nào — đánh dấu execution đang chạy nếu đã start.
                if task.get("started_at"):
                    states["task_execution"] = "RUNNING"
        elif overall in {"COMPLETED", "PARTIAL", "FAILED", "BLOCKED", "CANCELLED"}:
            # Không bịa COMPLETED cho từng phase khi thiếu event.
            pass
        return _finalize_phases_for_overall(states, overall)

    return _finalize_phases_for_overall(states, overall)


def _finalize_phases_for_overall(states: dict[str, str], overall: str) -> dict[str, str]:
    """Task đã kết thúc thì không để phase còn RUNNING (dữ liệu event thiếu/dở)."""
    if overall not in {"COMPLETED", "PARTIAL", "FAILED", "BLOCKED", "CANCELLED"}:
        return states
    closed = {
        "COMPLETED": "COMPLETED",
        "PARTIAL": "COMPLETED",
        "FAILED": "FAILED",
        "BLOCKED": "BLOCKED",
        "CANCELLED": "SKIPPED",
    }[overall]
    out = dict(states)
    for key, state in out.items():
        if state == "RUNNING":
            out[key] = closed
    return out


def _progress_line(phases: dict[str, str]) -> str:
    """Chỉ báo tiến độ khi đếm được phase đã kết thúc từ dữ liệu thật."""
    done_states = {"COMPLETED", "FAILED", "SKIPPED", "BLOCKED"}
    finished = sum(1 for state in phases.values() if state in done_states)
    started = sum(1 for state in phases.values() if state != "PENDING")
    if started == 0:
        return _NA
    return f"{finished}/{len(PHASE_DEFS)} phases reached a terminal state"


def _unescape_newlines(text: str) -> str:
    """Agent đôi khi trả `\\n` literal — đổi thành xuống dòng thật để Telegram đọc được."""
    if not text or "\\n" not in text:
        return text
    # Chỉ unescape khi mật độ `\\n` cao hơn newline thật (tránh đụng path Windows lạ).
    if text.count("\\n") >= max(2, text.count("\n")):
        return text.replace("\\r\\n", "\n").replace("\\n", "\n")
    return text


def _git_shortstat(text: str) -> str | None:
    match = _GIT_SHORTSTAT_RE.search(text or "")
    return match.group(0).strip() if match else None


def _looks_like_git_noise(text: str) -> bool:
    """Nhận diện dump git status / diff --stat — không nên in nguyên xi lên Telegram."""
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    if not lines:
        return False
    statish = sum(1 for ln in lines if _GIT_STAT_LINE_RE.search(ln) or ln.strip().startswith("??"))
    if _git_shortstat(text) and statish >= 3:
        return True
    return statish >= max(8, len(lines) // 2)


def _summarize_gitish(text: str, *, limit: int = 500) -> str:
    """Gom dump git dài thành vài dòng dễ đọc."""
    text = _unescape_newlines(text or "").strip()
    if not text:
        return _NR
    shortstat = _git_shortstat(text)
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
    untracked = [ln[2:].strip() for ln in lines if ln.startswith("??")]
    stat_rows = [ln.strip() for ln in lines if _GIT_STAT_LINE_RE.search(ln)]
    prose = [
        ln.strip()
        for ln in lines
        if not ln.startswith("??")
        and not _GIT_STAT_LINE_RE.search(ln)
        and not _GIT_SHORTSTAT_RE.fullmatch(ln.strip())
        and not ln.strip().startswith(("Git status", "Git diff", "diff --git"))
    ]
    parts: list[str] = []
    if shortstat:
        parts.append(shortstat)
    if untracked:
        sample = ", ".join(untracked[:3])
        more = f" (+{len(untracked) - 3} more)" if len(untracked) > 3 else ""
        parts.append(f"{len(untracked)} untracked: {sample}{more}")
    if stat_rows and not shortstat:
        parts.append(f"{len(stat_rows)} paths in diff --stat")
    if prose:
        # Giữ đoạn prose ngắn (audit / agent note), bỏ dòng nhiễu.
        keep = [p for p in prose if len(p) > 8][:6]
        if keep:
            parts.append("\n".join(keep))
    if not parts:
        return _clip(text, limit)
    return _clip("\n".join(parts), limit)


def _readable_body(text: str, *, limit: int = 500) -> str:
    """Chuẩn hoá body section trước khi đưa vào /status."""
    text = _unescape_newlines(text or "").strip()
    if not text:
        return _NR
    if _looks_like_git_noise(text):
        return _summarize_gitish(text, limit=limit)
    return _clip(text, limit)


def _extract_files_changed(events: list[dict[str, Any]], report: str) -> str:
    lines: list[str] = []
    patterns = (
        r"📄 Phát hiện file mới: (.+)",
        r"📝 Phát hiện file thay đổi: (.+)",
        r"🗑️ Phát hiện file đã biến mất: (.+)",
        r"📄 (.+)",
        r"📝 (.+)",
    )
    sources = [e.get("details") or "" for e in events]
    if report:
        sources.append(report)
    seen: set[str] = set()
    for source in sources:
        for pattern in patterns:
            for match in re.finditer(pattern, source):
                path = match.group(1).strip()
                if path and path not in seen and len(path) < 240:
                    seen.add(path)
                    lines.append(path)
    if not lines and report and "[FILE ACTIVITY SUMMARY]" in report:
        block = report.split("[FILE ACTIVITY SUMMARY]", 1)[1]
        for raw in block.splitlines():
            text = raw.strip()
            if text.startswith(("📄", "📝", "🗑️")):
                lines.append(text)
    # Fallback: tóm tắt từ git status / shortstat trong report (khi snapshot activity trống).
    if not lines and report:
        shortstat = _git_shortstat(report)
        untracked = [
            ln[2:].strip()
            for ln in report.splitlines()
            if ln.startswith("??") and ln[2:].strip()
        ]
        if shortstat or untracked:
            bits = []
            if shortstat:
                bits.append(shortstat)
            if untracked:
                bits.append(
                    f"{len(untracked)} untracked (e.g. "
                    + ", ".join(untracked[:5])
                    + ("…" if len(untracked) > 5 else "")
                    + ")"
                )
            return "\n".join(bits)
    if not lines:
        return _NR
    # Giữ danh sách gọn cho Telegram — mỗi file một dòng, không dùng bullet markdown.
    shown = lines[-15:]
    body = "\n".join(shown)
    if len(lines) > 15:
        body = f"… +{len(lines) - 15} earlier\n" + body
    return body


def _section_between(text: str, start: str, ends: tuple[str, ...]) -> str | None:
    if not text or start not in text:
        return None
    chunk = text.split(start, 1)[1]
    for end in ends:
        if end in chunk:
            chunk = chunk.split(end, 1)[0]
            break
    chunk = chunk.strip()
    return chunk or None


def _tests_summary(events: list[dict[str, Any]], report: str) -> str:
    for event in reversed(events):
        et = (event.get("event_type") or "").upper()
        if et in {"TESTING_FINISHED", "TESTING_FAILED", "TESTING_SKIPPED"}:
            details = (event.get("details") or "").strip()
            if details:
                return _readable_body(details, limit=700)
    section = _section_between(
        report,
        "KIỂM THỬ:",
        ("POST-TASK AUDIT", "KIỂM TRA GIT", "KIỂM TRA KHÔNG GHI"),
    )
    if section:
        return _readable_body(section, limit=700)
    if "Không áp dụng: chế độ đọc hiểu" in report:
        return "Skipped (analysis mode — tests not run)."
    return _NR


def _audit_summary(events: list[dict[str, Any]], report: str) -> str:
    for event in reversed(events):
        et = (event.get("event_type") or "").upper()
        if et in {"AUDIT_FINISHED", "AUDIT_FAILED", "AUDIT_SKIPPED"}:
            details = (event.get("details") or "").strip()
            if details:
                return _readable_body(details, limit=700)
    section = _section_between(
        report,
        "POST-TASK AUDIT (READ-ONLY):",
        ("KIỂM TRA GIT CỤC BỘ:", "KIỂM TRA GIT", "KIỂM TRA KHÔNG GHI"),
    )
    if section:
        return _readable_body(section, limit=700)
    section = _section_between(report, "POST-TASK AUDIT", ("KIỂM TRA GIT", "KIỂM TRA KHÔNG GHI"))
    if section:
        return _readable_body(section, limit=700)
    return _NR


def _execution_result(task: dict[str, Any], report: str) -> str:
    status = normalize_status(task.get("status"))
    if status == "QUEUED":
        return "Waiting for worker."
    if status == "RUNNING":
        step = task.get("current_step") or _NR
        return f"In progress — {step}"
    section = _section_between(
        report,
        "KẾT QUẢ TRIỂN KHAI:",
        ("KIỂM THỬ:", "POST-TASK AUDIT", "KIỂM TRA GIT"),
    )
    if section:
        return _readable_body(section, limit=700)
    section = _section_between(
        report,
        "BÁO CÁO PHÂN TÍCH CODEBASE:",
        ("KIỂM TRA KHÔNG GHI FILE:", "KIỂM TRA GIT"),
    )
    if section:
        return _readable_body(section, limit=700)
    if report.strip():
        # Report bị cắt mất header → tránh đổ nguyên dump git lên Telegram.
        return _readable_body(report.strip(), limit=700)
    return _NR


def _error_line(task: dict[str, Any], status: str) -> str:
    err = (task.get("error_text") or "").strip()
    if status not in {"FAILED", "BLOCKED", "PARTIAL"}:
        return _readable_body(err, limit=700) if err else _NR
    if not err:
        return _NR
    # PARTIAL thường nhét cả report (kèm git dump) vào error_text — chỉ giữ phần có ích.
    if _looks_like_git_noise(err):
        shortstat = _git_shortstat(err)
        if status == "PARTIAL":
            tip = "PARTIAL: tests/audit có cảnh báo — xem Tests / Post-task audit."
            return tip if not shortstat else f"{tip}\nGit: {shortstat}"
        return _summarize_gitish(err, limit=700)
    return _readable_body(err, limit=700)


def _remaining_work(
    task: dict[str, Any], status: str, phases: dict[str, str], report: str
) -> str:
    if status == "QUEUED":
        return "Waiting to be claimed by the worker."
    if status == "RUNNING":
        step = task.get("current_step") or "Unknown current step"
        return f"Finish current step: {step}"
    if status == "BLOCKED":
        return "Unblock the dependency / permission issue and re-run."
    if status in {"PARTIAL", "FAILED"}:
        # Chỉ lấy gợi ý nếu audit thật sự nêu remaining / gap.
        lowered = report.casefold()
        for marker in ("remaining", "còn lại", "gap", "chưa xong", "not done", "incomplete"):
            if marker in lowered:
                # Lấy đoạn quanh marker thay vì bịa nội dung.
                idx = lowered.index(marker)
                return report[max(0, idx - 80) : idx + 200].strip()
        pending = [
            label
            for key, label in PHASE_DEFS
            if phases.get(key) in {"PENDING", "RUNNING", "FAILED", "BLOCKED"}
        ]
        if pending:
            return "Phases still open: " + ", ".join(pending)
        return _NR
    return _NR


_PHASE_ICON = {
    "PENDING": "⬜",
    "RUNNING": "▶️",
    "COMPLETED": "✅",
    "FAILED": "❌",
    "SKIPPED": "⏭️",
    "BLOCKED": "🚫",
}


def _clip(text: str, limit: int = 500) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _block(title: str, body: str) -> list[str]:
    """Khối section Telegram: tiêu đề riêng, nội dung bên dưới — dễ quét hơn list gạch đầu dòng."""
    return ["", f"── {title} ──", _readable_body(body) if body else _NR]


def format_task_status(task: dict[str, Any], events: list[dict[str, Any]] | None = None) -> str:
    """Tạo nội dung /status đầy đủ lifecycle từ task + task_events."""
    events = events or []
    status = normalize_status(task.get("status"))
    icon = STATUS_ICON.get(status, "⚪")
    task_id = int(task["id"])
    report = _unescape_newlines(
        (task.get("report_text") or "") + "\n" + (task.get("error_text") or "")
    )
    phases = derive_phase_states(task, events)
    current_step = (task.get("current_step") or "").strip() or _NR
    if status == "RUNNING" and current_step == _NR:
        # Fallback: event PROGRESS / STARTED gần nhất.
        for event in reversed(events):
            et = (event.get("event_type") or "").upper()
            if et in PHASE_EVENTS:
                phase_key = PHASE_EVENTS[et][0]
                label = next(lbl for key, lbl in PHASE_DEFS if key == phase_key)
                current_step = label
                break
            if et in {"STARTED", "WORKER_STARTED", "PROGRESS"}:
                current_step = et
                break

    last_update = task.get("updated_at") or _latest_event_time(events) or _NR

    # Hàng tóm tắt căn cột bằng khoảng trắng — Telegram plain text, không markdown.
    summary = [
        f"📋 TASK-{task_id:04d} — TASK STATUS",
        "",
        f"Status      {icon} {status}",
        f"Project     {_project_label(task)}",
        f"Created     {_fmt_time(task.get('created_at'))}",
        f"Started     {_fmt_time(task.get('started_at'))}",
        f"Finished    {_fmt_time(task.get('finished_at'))}",
        f"Duration    {_fmt_duration(task.get('started_at'), task.get('finished_at'), status)}",
        f"Step        {current_step}",
        f"Updated     {_fmt_time(last_update) if last_update != _NR else _NR}",
        f"Progress    {_progress_line(phases)}",
    ]

    phase_lines = []
    for key, label in PHASE_DEFS:
        state = phases.get(key, "PENDING")
        phase_lines.append(f"{_PHASE_ICON.get(state, '⬜')} {label} — {state}")

    lines = summary + _block("Phases", "\n".join(phase_lines))
    lines += _block("Files changed", _extract_files_changed(events, report))
    lines += _block("Execution result", _execution_result(task, report))
    lines += _block("Tests", _tests_summary(events, report))
    lines += _block("Post-task audit", _audit_summary(events, report))
    lines += _block("Error", _error_line(task, status))
    lines += _block("Remaining work", _remaining_work(task, status, phases, report))

    text = "\n".join(lines)
    # Giữ phần đầu (summary + phases) — cắt đuôi nếu vượt giới hạn Telegram.
    if len(text) <= 3900:
        return text
    return text[:3899].rstrip() + "…"
