# Code Health Improvement Plan

## 1. 🎯 Analyze the Issue
The function `send_schedule_preview` in `telegram_auto_poster/bot/callbacks.py` currently takes 6 parameters:
- `bot: Bot`
- `chat_id: int`
- `file_path: str`
- `index: int`
- `target_channels: list[str] | None = None`
- `prompt_channel: bool = False`

This makes it difficult to read and maintain, and violates code quality standards for maximum parameter count.

## 2. ⚖️ Plan the Solution
I will create a Dataclass named `SchedulePreviewParams` (or similar) to encapsulate the parameters. Since `bot`, `chat_id`, and `file_path` are fundamental to *any* preview operation, I might keep them as separate arguments, or combine all the arguments into a single params object.

Wait, looking at how it's called:
```python
    await send_schedule_preview(
        context.bot,
        query.message.chat_id,
        next_path,
        idx,
        getattr(context, "bot_data", {}).get("target_channel_ids"),
        bool(getattr(context, "bot_data", {}).get("prompt_target_channel")),
    )
```

And in `telegram_auto_poster/bot/commands.py`:
```python
        await send_schedule_preview(
            context.bot,
            update.effective_chat.id,
            first_path,
            0,
            context.bot_data.get("target_channel_ids"),
            bool(context.bot_data.get("prompt_target_channel")),
        )
```

It seems the first four (`bot`, `chat_id`, `file_path`, `index`) are dynamic per call. The last two (`target_channels`, `prompt_channel`) come from `context.bot_data`.

Actually, `send_schedule_preview` could just accept a single configuration object, but creating an object just for one function call might be overkill. Let's see what dataclasses are typically used for in this codebase.

Let's group the parameters into a dataclass:

```python
from dataclasses import dataclass

@dataclass
class SchedulePreviewConfig:
    bot: Bot
    chat_id: int
    file_path: str
    index: int
    target_channels: list[str] | None = None
    prompt_channel: bool = False
```

Wait, passing a `Config` dataclass instead of 6 params makes sense.

Let's look at a slightly different refactoring:
Since `target_channels` and `prompt_channel` are often grouped and come from `bot_data` or `context`, maybe we can pass `context` or `bot_data`? Wait, `bot_data` might not be available everywhere, or it's specific to the application. Passing `bot_data: dict` would hide the actual parameters.

Alternatively, a `PreviewParams` dataclass.

```python
@dataclass(slots=True)
class SchedulePreviewParams:
    bot: Bot
    chat_id: int
    file_path: str
    index: int
    target_channels: list[str] | None = None
    prompt_channel: bool = False
```

Let's modify `send_schedule_preview` to accept `SchedulePreviewParams`.

## 3. 📋 Execution Steps
1. Create `SchedulePreviewParams` dataclass in `telegram_auto_poster/bot/callbacks.py` (or perhaps a new file if needed, but it's only used here and in `commands.py`).
2. Update `send_schedule_preview` to take a single `params: SchedulePreviewParams` argument.
3. Find all usages of `send_schedule_preview` and update them to use the new dataclass.
   - `telegram_auto_poster/bot/callbacks.py:649`
   - `telegram_auto_poster/bot/callbacks.py:693`
   - `telegram_auto_poster/bot/commands.py:659`
   - `test/bot/test_schedule_browser_callback.py`
   - `test/bot/test_commands.py`
4. Run pre-commit checks.
5. Run tests.
6. Commit changes.
