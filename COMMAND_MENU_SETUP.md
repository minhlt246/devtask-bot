# Telegram Command Menu

This build registers Telegram's native slash command menu automatically at startup using `set_my_commands`.

Commands:
- /start
- /projects
- /task
- /tasks
- /status
- /cancel
- /scanprojects
- /help

Install by replacing the `app` directory in `/Users/min/Desktop/devtask-bot` with this build's `app` directory. Keep `.env` and `data`. Restart with `python -m app.main`. Telegram may cache command suggestions briefly; reopen the chat or type `/` if the menu does not refresh immediately.

Note: this is Telegram's native command list. Project selection remains an inline keyboard after `/projects` or `/task`. It does not launch the coding agent yet.


## Added commands
- `/start`: enable the agent worker and show the welcome/help message.
- `/off`: pause claiming new tasks; queued tasks stay queued and an already-running task is allowed to finish. Telegram commands remain available so `/start` can resume work.
- `/clear`: does not erase task records or audit logs. Telegram Bot API cannot fetch and bulk-delete the entire chat history, so this command removes its own command message when possible and explains how to use Telegram's Clear History option.
