DEVTask Bot — Default Prompt Modes

This patch updates only the app folder. Keep the existing .env, data/, config/, virtual environment, and LaunchAgent/autostart files.

Install:
1. Stop the bot using the existing service helper (if installed): ./bot-service.sh stop
   Or stop the currently running foreground process with Ctrl+C.
2. Back up the current app folder.
3. Copy the app folder from this package into /Users/min/Desktop/devtask-bot/app and replace the old app folder.
4. Start the service again with ./bot-service.sh start, or run the existing startup command.

Modes:
- /readproject: force Prompt 1, read-only codebase analysis, no edits.
- /task: task execution using Prompt 2, followed by a separate read-only Prompt 3 audit.
- Natural requests clearly saying "đọc dự án", "đọc hiểu", "phân tích codebase", "lập bản đồ", "index codebase", "analyze codebase", etc. are auto-routed to analysis unless implementation verbs are present.
- Other /task requests default to implementation + post-task audit.

Prompt files live under app/prompts so replacing only app is sufficient.

Validation performed in the build environment:
- Python compileall: PASS.
- Prompt parser/load checks: PASS.
- Task mode classifier checks: PASS via isolated AST test.
- Telegram runtime/integration test: NOT RUN because python-telegram-bot is not installed in this build environment.

The code does not install dependencies, modify .env, touch the user's database, stage changes, or create commits.
