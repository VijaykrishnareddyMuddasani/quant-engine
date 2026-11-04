"""Operations: notifications, Telegram control, the kill switch, the rest-day guard, preflight
checks and the supervisor that runs a live book for a session."""

from quant_engine.ops.bot import BookInfo, CommandRouter, TelegramPoller, state_file_status
from quant_engine.ops.guard import GuardDecision, RestDayGuard, positions_in_state_files
from quant_engine.ops.killswitch import KillSwitch
from quant_engine.ops.notify import (
    ConsoleNotifier,
    MemoryNotifier,
    Notifier,
    TelegramBot,
    TelegramError,
    TelegramNotifier,
    chunks,
)
from quant_engine.ops.preflight import Check, CheckResult, report, run_checks
from quant_engine.ops.supervisor import BookSupervisor

__all__ = [
    "BookInfo",
    "BookSupervisor",
    "Check",
    "CheckResult",
    "CommandRouter",
    "ConsoleNotifier",
    "GuardDecision",
    "KillSwitch",
    "MemoryNotifier",
    "Notifier",
    "RestDayGuard",
    "TelegramBot",
    "TelegramError",
    "TelegramNotifier",
    "TelegramPoller",
    "chunks",
    "positions_in_state_files",
    "report",
    "run_checks",
    "state_file_status",
]
