"""
OXY Setup — Interactive, keyboard-driven onboarding wizard.

Features:
  - Rock-solid arrow-key navigation (↑ / ↓ / Enter / 1-9) with in-place ANSI rewriting
  - Clean international typography (English, Persian, Chinese) preserving native ligatures
  - Breadcrumb visual progress gauge inspired by Claude Code and Hermes Agent
  - Smart model presets for each provider (OpenAI, DeepSeek, Groq, Ollama, OpenRouter)
  - Hermes-style configuration summary dashboard
"""

from __future__ import annotations

import os
import sys
import time
from typing import Any

from rich.panel import Panel
from rich.table import Table
from rich import box

from .config import DEFAULT_CONFIG, CONFIG_FILE, save_config
from .render import console, get_theme, _mask_key
from .ui import select_menu, render_stepper, render_cockpit_header


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  i18n — Multilingual String Registry
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

LANG = {
    "en": {
        "welcome_title":    "OXY Setup",
        "welcome_sub":      "Autonomous AI Coding Agent · Interactive Configuration",
        "step":             "Step",
        "of":               "of",
        "done_title":       "Setup Complete!",
        "done_body":        "Configuration saved to [cyan]{path}[/].\nLaunch OXY anytime with: [bold cyan]python oxy.py[/]",

        # Steps
        "lang_title":       "Language Selection",
        "lang_desc":        "Choose your preferred interface language:",

        "provider_title":   "AI Provider",
        "provider_desc":    "Select your AI model provider:",
        "provider_hint":    "OXY connects to any OpenAI-compatible provider (DeepSeek, OpenAI, Groq, Ollama, OpenRouter).",

        "model_title":      "Model Selection",
        "model_desc":       "Select model or enter custom name:",
        "model_custom":     "Custom model...",
        "model_custom_desc":"Enter any other model identifier",

        "key_title":        "Authentication Key",
        "key_desc":         "Enter API key:",
        "key_hint":         "Stored locally in oxy_config.json. System environment variables are also supported.",

        "theme_title":      "Cockpit Theme",
        "theme_desc":       "Select terminal interface style:",

        "security_title":   "Security & Permissions",
        "security_desc":    "Choose how tool actions (file edits, bash execution) are authorized:",

        "adv_title":        "Advanced Parameters",
        "adv_desc":         "Tune memory and inference parameters?",
        "adv_history":      "Conversation memory window (turns)",
        "adv_temperature":  "Sampling temperature (0.0 = precise, 1.0 = creative)",
        "adv_max_tokens":   "Max tokens per response",
    },

    "fa": {
        "welcome_title":    "راه‌اندازی تعاملی OXY",
        "welcome_sub":      "دستیار هوشمند برنامه‌نویسی · پیکربندی سیستم",
        "step":             "مرحله",
        "of":               "از",
        "done_title":       "راه‌اندازی با موفقیت انجام شد!",
        "done_body":        "فایل پیکربندی در [cyan]{path}[/] ذخیره شد.\nبرای اجرای ایجنت: [bold cyan]python oxy.py[/]",

        "lang_title":       "انتخاب زبان",
        "lang_desc":        "زبان مورد نظر خود را انتخاب کنید:",

        "provider_title":   "سرویس‌دهنده هوش مصنوعی",
        "provider_desc":    "مدل شما در کدام سرویس میزبانی می‌شود؟",
        "provider_hint":    "اوکسی با تمام سرویس‌های سازگار با OpenAI کار می‌کند (DeepSeek, OpenAI, Groq, Ollama).",

        "model_title":      "انتخاب مدل",
        "model_desc":       "مدل مورد نظر را انتخاب کرده یا شناسه دلخواه وارد کنید:",
        "model_custom":     "مدل سفارشی...",
        "model_custom_desc":"ورود دستی نام مدل",

        "key_title":        "کلید احراز هویت (API Key)",
        "key_desc":         "کلید API را وارد کنید:",
        "key_hint":         "کلید به صورت محلی در oxy_config.json ذخیره می‌شود.",

        "theme_title":      "تم ظاهری ترمینال",
        "theme_desc":       "استایل بصری مورد علاقه خود را انتخاب کنید:",

        "security_title":   "امنیت و سطح دسترسی ابزارها",
        "security_desc":    "نحوه تایید اجرای دستورات شل و ویرایش فایل‌ها:",

        "adv_title":        "تنظیمات پیشرفته",
        "adv_desc":         "آیا مایل به شخصی‌سازی پارامترهای مدل هستید؟",
        "adv_history":      "تعداد پیام‌های حافظه مکالمه",
        "adv_temperature":  "دمای خلاقیت (۰.۰ = دقیق، ۱.۰ = خلاق)",
        "adv_max_tokens":   "حداکثر توکن در هر پاسخ",
    },

    "zh": {
        "welcome_title":    "OXY 设置向导",
        "welcome_sub":      "自主 AI 编程智能体 · 交互式配置",
        "step":             "步骤",
        "of":               "/",
        "done_title":       "配置完成！",
        "done_body":        "配置已保存至 [cyan]{path}[/]\n运行 [bold cyan]python oxy.py[/] 启动。",

        "lang_title":       "语言选择",
        "lang_desc":        "请选择偏好语言：",

        "provider_title":   "AI 服务商",
        "provider_desc":    "选择模型服务商：",
        "provider_hint":    "支持所有 OpenAI 兼容接口（DeepSeek, OpenAI, Groq, Ollama 等）。",

        "model_title":      "选择模型",
        "model_desc":       "选择模型或输入自定义名称：",
        "model_custom":     "自定义模型...",
        "model_custom_desc":"手动输入模型标识符",

        "key_title":        "API 认证密钥",
        "key_desc":         "请输入 API Key：",
        "key_hint":         "保存在本地 oxy_config.json。",

        "theme_title":      "界面视觉主题",
        "theme_desc":       "选择外观风格：",

        "security_title":   "安全与执行权限",
        "security_desc":    "工具执行确认策略：",

        "adv_title":        "高级推理参数",
        "adv_desc":         "是否微调推理参数？",
        "adv_history":      "历史对话轮数",
        "adv_temperature":  "采样温度 (0.0 = 精确, 1.0 = 创意)",
        "adv_max_tokens":   "单次最大 token 数",
    },
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Provider & Model Catalog
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PROVIDERS = [
    {
        "name": "DeepSeek",
        "desc": "DeepSeek V3 & R1 reasoning",
        "url": "https://api.deepseek.com/v1",
        "models": [
            ("deepseek-chat", "DeepSeek-V3 flagship general & coding"),
            ("deepseek-reasoner", "DeepSeek-R1 full reasoning & thought"),
        ],
        "default_model": "deepseek-chat",
        "env_key": "DEEPSEEK_API_KEY",
    },
    {
        "name": "OpenAI",
        "desc": "Official OpenAI API (GPT-4o, o3-mini, o1)",
        "url": "https://api.openai.com/v1",
        "models": [
            ("gpt-4o-mini", "Fast, smart, lightweight default"),
            ("gpt-4o", "Flagship multimodal intelligence"),
            ("o3-mini", "High-performance coding & reasoning"),
            ("o1", "Deep reasoning for complex architecture"),
        ],
        "default_model": "gpt-4o-mini",
        "env_key": "OPENAI_API_KEY",
    },
    {
        "name": "Groq",
        "desc": "Ultra-fast LPU inference (~300+ tokens/sec)",
        "url": "https://api.groq.com/openai/v1",
        "models": [
            ("llama-3.3-70b-versatile", "Llama 3.3 70B on Groq LPU"),
            ("deepseek-r1-distill-llama-70b", "DeepSeek R1 reasoning on Groq LPU"),
            ("llama-3.1-8b-instant", "Ultra-fast instant coding & chat"),
        ],
        "default_model": "llama-3.3-70b-versatile",
        "env_key": "GROQ_API_KEY",
    },
    {
        "name": "OpenRouter",
        "desc": "Unified router (Claude, GPT, DeepSeek, Mistral)",
        "url": "https://openrouter.ai/api/v1",
        "models": [
            ("anthropic/claude-3.7-sonnet", "Claude 3.7 Sonnet with hybrid reasoning"),
            ("deepseek/deepseek-r1", "DeepSeek R1 full reasoning via OpenRouter"),
            ("openai/gpt-4o-mini", "OpenAI GPT-4o mini via OpenRouter"),
            ("meta-llama/llama-3.3-70b-instruct", "Llama 3.3 70B Instruct"),
        ],
        "default_model": "anthropic/claude-3.7-sonnet",
        "env_key": "OPENROUTER_API_KEY",
    },
    {
        "name": "Together AI",
        "desc": "Cloud open-source infrastructure",
        "url": "https://api.together.xyz/v1",
        "models": [
            ("meta-llama/Llama-3.3-70B-Instruct-Turbo", "Llama 3.3 70B Turbo"),
            ("deepseek-ai/DeepSeek-R1", "DeepSeek R1 on Together cluster"),
            ("Qwen/Qwen2.5-Coder-32B-Instruct", "Qwen 2.5 Coder 32B specialized coding model"),
        ],
        "default_model": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        "env_key": "TOGETHER_API_KEY",
    },
    {
        "name": "Local (Ollama)",
        "desc": "On-device private inference (localhost:11434)",
        "url": "http://localhost:11434/v1",
        "models": [
            ("qwen2.5-coder:latest", "Qwen 2.5 Coder for programming"),
            ("llama3.1:latest", "Meta Llama 3.1 instruct"),
            ("deepseek-r1:latest", "DeepSeek R1 distilled reasoning"),
        ],
        "default_model": "qwen2.5-coder:latest",
        "env_key": "",
    },
    {
        "name": "Local (LM Studio)",
        "desc": "Local GUI server (localhost:1234)",
        "url": "http://localhost:1234/v1",
        "models": [
            ("local-model", "Active loaded model in LM Studio GUI"),
        ],
        "default_model": "local-model",
        "env_key": "",
    },
    {
        "name": "Custom Endpoint",
        "desc": "Custom OpenAI-compatible URL",
        "url": "",
        "models": [],
        "default_model": "",
        "env_key": "",
    },
]

def _build_themes_info():
    """Build theme options from registry: builtins first, then user custom themes."""
    builtin_info = [
        ("cyber",   "Cyber",    "Electric cyan & neon green matrix style"),
        ("aurora",  "Aurora",   "Northern lights violet & emerald gradients"),
        ("minimal", "Minimal",  "Clean monochrome for focused terminal setups"),
    ]
    try:
        from .render import THEME_REGISTRY, list_themes
        THEME_REGISTRY.reload()
        builtin_slugs = {slug for slug, _, _ in builtin_info}
        for slug in list_themes():
            if slug not in builtin_slugs:
                theme = THEME_REGISTRY.get(slug)
                builtin_info.append((slug, theme.get("name", slug).title(), "Custom user theme"))
    except Exception:
        pass
    return builtin_info


THEMES_INFO = _build_themes_info()

PERMISSION_OPTIONS = [
    ("ask",  "Interactive (Recommended)", "Confirm file mutations and bash command execution"),
    ("auto", "Autonomous (YOLO)",          "Execute tools autonomously (Hardline floor active)"),
]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Input Helpers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _ask_input(prompt_text: str, default: str = "", password: bool = False, theme: dict = None) -> str:
    """Prompt user for clean single-line text input."""
    from .compat import flush_input
    flush_input()

    accent = theme.get("accent", "cyan") if theme else "cyan"
    display_def = "****" if password and default else default

    if default:
        console.print(f"  [{accent}]?[/] [bold white]{prompt_text}[/] [dim]({display_def})[/]")
    else:
        console.print(f"  [{accent}]?[/] [bold white]{prompt_text}[/]")

    try:
        val = console.input("  › ").strip()
    except (KeyboardInterrupt, EOFError):
        console.print()
        raise SystemExit(0)

    return val or default


def _ask_yes_no(prompt_text: str, default: bool = False, theme: dict = None) -> bool:
    """Ask interactive yes/no question using select menu."""
    opts = [
        ("No", "Keep default values"),
        ("Yes", "Fine-tune advanced settings"),
    ] if not default else [
        ("Yes", "Fine-tune advanced settings"),
        ("No", "Keep default values"),
    ]
    idx = select_menu(prompt_text, opts, default=0, theme=theme)
    chosen_label, _ = opts[idx]
    return chosen_label == "Yes"


def _animate_setup_complete():
    """Clean animated initialization sequence."""
    if not sys.stdout.isatty():
        return
    green = "\033[1;32m"
    dim = "\033[2m"
    reset = "\033[0m"

    steps = [
        "Parallel execution planner",
        "Security floor",
        "KV prefix cache",
        "Transaction ledger",
    ]
    sys.stdout.write("\n")
    for step in steps:
        sys.stdout.write(f"  {dim}· {step}...{reset}\r")
        sys.stdout.flush()
        time.sleep(0.05)
        sys.stdout.write(f"  {green}✔{reset} {dim}{step}{reset}\n")
        sys.stdout.flush()
    sys.stdout.write("\n")
    sys.stdout.flush()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Interactive Setup Wizard
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def setup_wizard() -> dict[str, Any]:
    """Run the interactive, keyboard-driven onboarding wizard."""
    config = DEFAULT_CONFIG.copy()
    total_steps = 6
    theme = get_theme("cyber")

    # ── Cockpit Header ─────────────────────────────────────────
    render_cockpit_header(theme)

    # ── Step 1: Language ───────────────────────────────────────
    lang_options = [
        ("English",  "English"),
        ("فارسی",    "زبان فارسی"),
        ("中文",      "简体中文"),
    ]

    render_stepper(1, total_steps, "Language Selection / انتخاب زبان", theme)
    lang_idx = select_menu(
        title="Select Language / انتخاب زبان",
        options=lang_options,
        default=0,
        theme=theme,
        step_info="Step 1/6",
    )

    lang_code = ["en", "fa", "zh"][lang_idx]
    config["language"] = lang_code
    try:
        from .i18n import set_language
        set_language(lang_code)
    except Exception:
        pass
    s = LANG[lang_code]

    if lang_code == "fa":
        config["system_prompt"] = (
            "شما OXY هستید، یک ایجنت حرفه‌ای برنامه‌نویسی و دستیار هوشمند. "
            "همواره به زبان فارسی دقیق، شیوا و روان پاسخ دهید."
        )
    elif lang_code == "zh":
        config["system_prompt"] = (
            "你是 OXY，一个专业的编程智能体和智能助手。请使用流利、清晰的中文进行回复。"
        )

    # ── Step 2: Provider ───────────────────────────────────────
    render_stepper(2, total_steps, s["provider_title"], theme)
    provider_opts = [(p_item["name"], p_item["desc"]) for p_item in PROVIDERS]
    provider_idx = select_menu(
        title=s["provider_title"],
        options=provider_opts,
        default=0,
        theme=theme,
        step_info="Step 2/6",
    )
    provider = PROVIDERS[provider_idx]

    if provider["name"] == "Custom Endpoint":
        config["base_url"] = _ask_input("Enter Base URL", "http://localhost:8000/v1", theme=theme)
    else:
        config["base_url"] = provider["url"]

    # ── Step 3: Model ──────────────────────────────────────────
    render_stepper(3, total_steps, s["model_title"], theme)
    preset_models = provider.get("models", [])

    if preset_models:
        model_options = [(m_name, m_desc) for m_name, m_desc in preset_models]
        model_options.append((s["model_custom"], s["model_custom_desc"]))

        model_idx = select_menu(
            title=s["model_title"],
            options=model_options,
            default=0,
            theme=theme,
            step_info="Step 3/6",
        )

        chosen_name, _ = model_options[model_idx]
        if chosen_name == s["model_custom"]:
            config["model"] = _ask_input(s["model_desc"], default=provider["default_model"] or "gpt-4o-mini", theme=theme)
        else:
            config["model"] = chosen_name
    else:
        config["model"] = _ask_input(s["model_desc"], default="gpt-4o-mini", theme=theme)

    # ── Step 4: Authentication Key ─────────────────────────────
    render_stepper(4, total_steps, s["key_title"], theme)

    env_var_to_check = provider.get("env_key") or "OPENAI_API_KEY"
    found_env_val = os.environ.get(env_var_to_check, "") or os.environ.get("OPENAI_API_KEY", "")

    if provider["name"].startswith("Local"):
        config["api_key"] = "not-needed"
        console.print("  [bold green]✔[/] [dim]Local provider selected — no authentication key required.[/]\n")
    elif found_env_val:
        masked_env = found_env_val[:4] + "..." + found_env_val[-4:] if len(found_env_val) > 8 else "****"
        console.print(f"  [bold green]✔[/] [dim]Detected {env_var_to_check}:[/] [bold cyan]{masked_env}[/]")
        use_env = _ask_yes_no("Use detected environment key?", default=True, theme=theme)
        if use_env:
            config["api_key"] = found_env_val
        else:
            config["api_key"] = _ask_input(s["key_desc"], default="", password=True, theme=theme)
    else:
        key = _ask_input(s["key_desc"], default="", password=True, theme=theme)
        config["api_key"] = key

    # ── Step 5: Theme ──────────────────────────────────────────
    render_stepper(5, total_steps, s["theme_title"], theme)
    theme_opts = [(name, desc) for _, name, desc in THEMES_INFO]
    theme_idx = select_menu(
        title=s["theme_title"],
        options=theme_opts,
        default=0,
        theme=theme,
        step_info="Step 5/6",
    )
    chosen_theme_key = THEMES_INFO[theme_idx][0]
    config["theme"] = chosen_theme_key
    theme = get_theme(chosen_theme_key)

    # ── Step 6: Security & Permissions ─────────────────────────
    render_stepper(6, total_steps, s["security_title"], theme)
    perm_idx = select_menu(
        title=s["security_title"],
        options=[(label, desc) for _, label, desc in PERMISSION_OPTIONS],
        default=0,
        theme=theme,
        step_info="Step 6/6",
    )
    config["permission_mode"] = PERMISSION_OPTIONS[perm_idx][0]

    # Optional fine-tuning parameters
    if _ask_yes_no(s["adv_desc"], default=False, theme=theme):
        hist_val = _ask_input(s["adv_history"], str(config["max_history"]), theme=theme)
        try:
            config["max_history"] = int(hist_val)
        except ValueError:
            pass

        temp_val = _ask_input(s["adv_temperature"], str(config["temperature"]), theme=theme)
        try:
            config["temperature"] = float(temp_val)
        except ValueError:
            pass

        tok_val = _ask_input(s["adv_max_tokens"], str(config["max_tokens"]), theme=theme)
        try:
            config["max_tokens"] = int(tok_val)
        except ValueError:
            pass

    # ── Animated Subsystem Initialization ──────────────────────
    _animate_setup_complete()

    # ── Save Configuration ─────────────────────────────────────
    save_config(config)

    # ── Configuration Summary ──────────────────────────────────
    console.print()
    t = Table.grid(padding=(0, 2))
    t.add_column(style="dim", justify="right")
    t.add_column(style="bold white")

    t.add_row("language", lang_options[lang_idx][0])
    t.add_row("provider", provider["name"])
    t.add_row("endpoint", config["base_url"])
    t.add_row("model", config["model"])
    t.add_row("key", _mask_key(config["api_key"]))
    t.add_row("theme", chosen_theme_key)
    t.add_row("security", config["permission_mode"])
    t.add_row("tools", "[green]9 active[/]")
    t.add_row("config", CONFIG_FILE)

    console.print(Panel(
        t,
        title=f"[bold green]✔ {s['done_title']}[/]",
        border_style="green",
        box=box.ROUNDED,
        padding=(0, 1),
    ))
    console.print()
    console.print("  [dim]Run[/] [bold cyan]python3 oxy.py[/] [dim]to start[/]\n")

    return config
