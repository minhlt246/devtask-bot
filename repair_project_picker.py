#!/usr/bin/env python3
"""Repair the DevTask Telegram project picker. Run from the project root."""
from datetime import datetime
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path.cwd()
TASK = ROOT / "app" / "handlers" / "task_commands.py"
MAIN = ROOT / "app" / "main.py"
PLIST = Path.home() / "Library" / "LaunchAgents" / "com.devtask.bot.plist"


def die(message):
    print("ERROR:", message, file=sys.stderr)
    raise SystemExit(1)


def remove_function(source, name, occurrence=0):
    matches = list(re.finditer(rf"(?m)^async def {re.escape(name)}\(", source))
    if occurrence >= len(matches):
        die(f"Cannot find occurrence {occurrence + 1} of {name}().")
    start = matches[occurrence].start()
    nxt = re.search(r"(?m)^(?:async )?def \w+\(", source[start + 1:])
    end = start + 1 + nxt.start() if nxt else len(source)
    while end < len(source) and source[end] in "\r\n":
        end += 1
    return source[:start] + source[end:]


def main():
    if not TASK.is_file() or not MAIN.is_file():
        die("Run from ~/Desktop/devtask-bot, the project root.")

    old_task = TASK.read_text()
    old_main = MAIN.read_text()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    task_backup = TASK.with_name(f"task_commands.py.before-picker-repair-{stamp}")
    main_backup = MAIN.with_name(f"main.py.before-picker-repair-{stamp}")
    shutil.copy2(TASK, task_backup)
    shutil.copy2(MAIN, main_backup)
    print("Backups:", task_backup, main_backup, sep="\n  ")

    task = old_task.replace(
        r"from telegram.ext import (\n    CommandHandler,",
        "from telegram.ext import (\n    CommandHandler,",
    )
    definitions = list(re.finditer(r"(?m)^async def projects_select_start\(", task))
    if not definitions:
        die("projects_select_start() not found; no source files changed.")
    while len(re.findall(r"(?m)^async def projects_select_start\(", task)) > 1:
        task = remove_function(task, "projects_select_start", 1)

    if re.search(r"(?m)^async def _send_project_pages\(", task):
        task = remove_function(task, "_send_project_pages", 0)

    if len(re.findall(r"(?m)^async def projects_select_start\(", task)) != 1:
        die("Duplicate projects_select_start() remains.")
    if "_send_project_pages(" in task:
        die("Reference to _send_project_pages() remains.")
    if "ReplyKeyboardMarkup" not in task or "_project_reply_keyboard(projects, context)" not in task:
        die("Expected 3-column ReplyKeyboard picker not found.")
    if "async def clear_history_command" not in task or "clear_history_command" not in old_main:
        die("/clearhistory was not found; refusing to overwrite source.")

    new_main = old_main.replace(
        'BotCommand("projects", "📁 Danh sách dự án dạng văn bản")',
        'BotCommand("projects", "📁 Chọn dự án bằng nút 3 cột")',
    )
    TASK.write_text(task)
    MAIN.write_text(new_main)

    check = subprocess.run([
        str(ROOT / ".venv" / "bin" / "python"), "-m", "py_compile",
        str(TASK), str(MAIN)
    ], cwd=ROOT)
    if check.returncode:
        TASK.write_text(old_task)
        MAIN.write_text(old_main)
        die("Syntax check failed; both original source files were restored.")

    print("PASS: syntax valid; one picker handler; list fallback helper removed; /clearhistory preserved.")

    uid = subprocess.run(["id", "-u"], capture_output=True, text=True, check=True).stdout.strip()
    service = f"gui/{uid}/com.devtask.bot"
    registered = subprocess.run(
        ["launchctl", "print", service],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    ).returncode == 0
    if registered:
        restart = subprocess.run(["launchctl", "kickstart", "-k", service], cwd=ROOT)
    elif PLIST.is_file():
        restart = subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", str(PLIST)], cwd=ROOT)
    else:
        print("Source fixed; LaunchAgent plist not found, so bot was not restarted.")
        return
    if restart.returncode:
        print("Source fixed, but LaunchAgent restart failed. Inspect:", service)
        raise SystemExit(restart.returncode)
    print("LaunchAgent restart requested. Test /projects and /refresh in Telegram.")


if __name__ == "__main__":
    main()
