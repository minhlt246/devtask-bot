# Antigravity integration (MVP)

This version runs queued tasks with `agy -p` in the selected project folder, runs a recognized local test command when available, and records a report in SQLite. It does not commit changes or deploy.

## Install/update the existing bot

1. Stop the running bot with `Ctrl+C` in its Terminal.
2. Back up the current project folder (especially `.env` and `data/`).
3. Replace only the `app` folder with the `app` folder from this package. Keep your existing `.env`, `data/`, and any personal configuration.
4. In `.env`, add or verify:

   ```env
   AGY_COMMAND=/Users/min/.local/bin/agy
   AGENT_TIMEOUT_SECONDS=1800
   TEST_TIMEOUT_SECONDS=300
   ```

5. Start it:

   ```bash
   cd /Users/min/Desktop/devtask-bot
   source .venv/bin/activate
   python -m app.main
   ```

6. In Telegram, select a small test project and send a low-risk task, e.g. `Inspect the project and report its structure. Do not edit files.`

## Safety limits

- Only the authorized Telegram user can issue bot commands.
- Worker accepts paths discovered under ordinary user folders and revalidates the project before launch.
- No shell is used to invoke `agy`; task text is passed as a prompt argument.
- Worker has a timeout; tests are attempted only when a supported project marker is detected.
- It does not auto-install dependencies, commit, push, deploy, or use a blanket permission-bypass option.
- A coding agent can still make mistakes. Use a Git-backed project and inspect the diff before keeping changes.

## Known MVP limitations

- Worker processes one task at a time.
- Test detection is deliberately simple and may need adjustment for a particular repository.
- A task may be reported as `SUCCEEDED` when the agent process exits successfully even if its own test command fails; inspect the test report and Git diff before accepting the work.
- This integration uses the exact `agy -p` interface verified on the user's machine; CLI behavior may change with future updates.
