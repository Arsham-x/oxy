"""
OXY i18n — Multilingual string registry and localization manager.

Supports English (en), Persian (fa), and Chinese (zh) for REPL chrome,
tool authorization prompts, status messages, and onboarding dialogs.
"""

from __future__ import annotations

import os


DEFAULT_LANGUAGE = "en"
SUPPORTED_LANGUAGES = ("en", "fa", "zh")


STRINGS: dict[str, dict[str, str]] = {
    "en": {
        # General & Status
        "app_title": "OXY",
        "app_subtitle": "Autonomous AI Coding Agent · Zero Bloat",
        "welcome_hint": "Enter send · Alt+Enter newline · Ctrl+C cancel · /help commands",
        "turns": "turns",
        "tok": "tok",
        "files": "files",
        "mem": "mem",
        "rr": "rr",
        "auto": "auto",
        "ask": "ask",
        "help_shortcut": "/help",

        # Permissions & Confirmations
        "allow_action": "Allow this action?",
        "action_prompt": "Action:",
        "yes_once": "[bold green]y[/]es",
        "yes_always": "[bold cyan]a[/]lways for session",
        "no": "[bold red]n[/]o",
        "choice_prompt": "[y/n/a]",
        "confirm_question": "Continue?",
        "cancelled_by_user": "cancelled by user",
        "denied_by_user": "denied by user",
        "blocked_by_hook": "blocked by hook",

        # Goodbye & Telemetry
        "goodbye_title": "Session Summary",
        "goodbye_turns": "turns completed",
        "goodbye_tokens": "total tokens used",
        "goodbye_elapsed": "elapsed time",
        "goodbye_bye": "Goodbye!",

        # Errors & Warnings
        "error_title": "Error",
        "agent_error": "Agent error",
        "command_failed": "Command failed",
        "missing_api_key": "No API key configured.",
        "orphaned_tool_calls": "Previous session ended with {count} unresolved tool call(s) (interrupted or crashed).",
        "discarded_orphans": "Discarded {count} orphaned tool call(s). State is clean.",
        "history_preserved": "history preserved ({count} messages). keep going.",
        "resumed_session": "Resumed session '{session_id}' ({count} turns)",
    },

    "fa": {
        # General & Status
        "app_title": "اوکسی",
        "app_subtitle": "دستیار هوشمند برنامه‌نویسی و کدنویسی خودکار · معماری سبک و سریع",
        "welcome_hint": "ارسال: Enter · خط جدید: Alt+Enter · لغو: Ctrl+C · راهنما: /help",
        "turns": "پیام",
        "tok": "توکن",
        "files": "فایل",
        "mem": "حافظه",
        "rr": "چرخشی",
        "auto": "خودکار",
        "ask": "تایید",
        "help_shortcut": "راهنما /help",

        # Permissions & Confirmations
        "allow_action": "اجازه اجرای این عملیات را می‌دهید؟",
        "action_prompt": "عملیات:",
        "yes_once": "[bold green]ب[/]له (یک‌بار)",
        "yes_always": "[bold cyan]هـ[/]میشه برای این نشست",
        "no": "[bold red]خ[/]یر",
        "choice_prompt": "[بله/خیر/همیشه]",
        "confirm_question": "آیا ادامه می‌دهید؟",
        "cancelled_by_user": "توسط کاربر لغو شد",
        "denied_by_user": "توسط کاربر رد شد",
        "blocked_by_hook": "توسط قلاب امنیتی مسدود شد",

        # Goodbye & Telemetry
        "goodbye_title": "گزارش نشست",
        "goodbye_turns": "پیام‌های تبادل شده",
        "goodbye_tokens": "مجموع توکن‌های مصرفی",
        "goodbye_elapsed": "مدت زمان نشست",
        "goodbye_bye": "خداحافظ و موفق باشید!",

        # Errors & Warnings
        "error_title": "خطا",
        "agent_error": "خطای پردازش ایجنت",
        "command_failed": "دستور با شکست مواجه شد",
        "missing_api_key": "کلید API تنظیم نشده است.",
        "orphaned_tool_calls": "نشست قبلی دارای {count} فراخوانی ابزار ناتمام است (کرش یا قطعی).",
        "discarded_orphans": "{count} فراخوانی ناتمام پاکسازی شد. وضعیت امن است.",
        "history_preserved": "تاریخچه مکالمه حفظ شد ({count} پیام). می‌توانید ادامه دهید.",
        "resumed_session": "نشست '{session_id}' بازیابی شد ({count} پیام)",
    },

    "zh": {
        # General & Status
        "app_title": "OXY",
        "app_subtitle": "自主 AI 编程智能体 · 极简高性能架构",
        "welcome_hint": "Enter 发送 · Alt+Enter 换行 · Ctrl+C 取消 · /help 查看指令",
        "turns": "轮对话",
        "tok": "词元",
        "files": "文件",
        "mem": "记忆",
        "rr": "轮换",
        "auto": "自动",
        "ask": "询问",
        "help_shortcut": "/help 帮助",

        # Permissions & Confirmations
        "allow_action": "是否允许执行此操作？",
        "action_prompt": "操作：",
        "yes_once": "[bold green]y[/] 允许本次",
        "yes_always": "[bold cyan]a[/] 本次会话始终允许",
        "no": "[bold red]n[/] 拒绝",
        "choice_prompt": "[y/n/a]",
        "confirm_question": "是否继续？",
        "cancelled_by_user": "用户已取消",
        "denied_by_user": "用户已拒绝",
        "blocked_by_hook": "已被生命周期钩子阻止",

        # Goodbye & Telemetry
        "goodbye_title": "会话统计总结",
        "goodbye_turns": "完成对话轮次",
        "goodbye_tokens": "累计消耗词元",
        "goodbye_elapsed": "总耗时",
        "goodbye_bye": "再见！祝编码愉快！",

        # Errors & Warnings
        "error_title": "错误",
        "agent_error": "智能体错误",
        "command_failed": "命令执行失败",
        "missing_api_key": "未配置 API 密钥。",
        "orphaned_tool_calls": "上个会话遗留了 {count} 个未决工具调用（崩溃或中断）。",
        "discarded_orphans": "已清理 {count} 个孤儿工具调用。状态已重置。",
        "history_preserved": "已保留对话历史（{count} 轮）。请继续。",
        "resumed_session": "已恢复会话 '{session_id}'（加载了 {count} 轮对话）",
    },
}


class LanguageManager:
    """Manages active language selection and string translation lookup."""

    def __init__(self, default_lang: str = DEFAULT_LANGUAGE):
        self._active_lang = default_lang

    @property
    def language(self) -> str:
        return self._active_lang

    @language.setter
    def language(self, code: str):
        normalized = (code or "").lower().strip()
        if normalized in SUPPORTED_LANGUAGES:
            self._active_lang = normalized
        else:
            self._active_lang = DEFAULT_LANGUAGE

    def t(self, key: str, lang: str | None = None, **kwargs) -> str:
        """Translate key into target language, falling back to English, with string interpolation."""
        target_lang = (lang or self._active_lang or DEFAULT_LANGUAGE).lower().strip()
        lang_dict = STRINGS.get(target_lang, STRINGS[DEFAULT_LANGUAGE])

        template = lang_dict.get(key) or STRINGS[DEFAULT_LANGUAGE].get(key) or key
        if kwargs:
            try:
                return template.format(**kwargs)
            except Exception:
                return template
        return template


# Global language manager singleton
I18N = LanguageManager(os.environ.get("OXY_LANG", DEFAULT_LANGUAGE))


def t(key: str, lang: str | None = None, **kwargs) -> str:
    """Shorthand for global I18N.t()."""
    return I18N.t(key, lang=lang, **kwargs)


def set_language(lang_code: str):
    """Set global active language."""
    I18N.language = lang_code
