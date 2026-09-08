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
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

from .config import DEFAULT_CONFIG, CONFIG_FILE, SYSTEM_PROMPT_FILE, save_config
from .render import get_theme, _mask_key
from .ui import select_menu, render_stepper, render_cockpit_header, p

console = Console()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  i18n — Multilingual String Registry
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

LANG = {
    "en": {
        "welcome_title":    "Welcome to OXY Setup",
        "welcome_sub":      "Autonomous AI Coding Agent · Interactive Configuration",
        "step":             "Step",
        "of":               "of",
        "done_title":       "Setup Complete!",
        "done_body":        "Configuration saved to [cyan]{path}[/].\nLaunch OXY anytime with: [bold cyan]python oxy.py[/]",

        # Steps
        "lang_title":       "Language Selection",
        "lang_desc":        "Choose your preferred interface language:",

        "provider_title":   "AI Provider",
        "provider_desc":    "Select where your AI model is hosted:",
        "provider_hint":    "OXY works with any OpenAI-compatible API (OpenAI, DeepSeek, Groq, Ollama, OpenRouter).",

        "model_title":      "Model Selection",
        "model_desc":       "Select model or enter custom name:",
        "model_custom":     "Custom model...",
        "model_custom_desc":"Enter any other model identifier",

        "key_title":        "Authentication Key",
        "key_desc":         "Enter your API key:",
        "key_hint":         "Stored locally in oxy_config.json. You can also use system environment variables.",

        "theme_title":      "Visual Interface Theme",
        "theme_desc":       "Select your terminal cockpit style:",

        "security_title":   "Tool Security & Permissions",
        "security_desc":    "Choose how tool actions (file edits, bash execution) are authorized:",

        "adv_title":        "Advanced Parameters",
        "adv_desc":         "Tune memory and inference parameters?",
        "adv_history":      "Conversation memory window (turns)",
        "adv_temperature":  "Sampling temperature (0.0 = precise, 1.0 = creative)",
        "adv_max_tokens":   "Max tokens per response",
    },

    "fa": {
        "welcome_title":    "به ویزارد راه‌اندازی OXY خوش آمدید",
        "welcome_sub":      "دستیار هوشمند برنامه‌نویسی · تنظیمات تعاملی سیستم",
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
        "model_desc":       "مدل پیشنهادی را انتخاب کرده یا مدل دلخواه وارد کنید:",
        "model_custom":     "مدل سفارشی...",
        "model_custom_desc":"تایپ نام و شناسه مدل دلخواه",

        "key_title":        "کلید احراز هویت (API Key)",
        "key_desc":         "کلید API را وارد کنید:",
        "key_hint":         "کلید به صورت امن در oxy_config.json ذخیره می‌شود و مستقیماً به ارائه‌دهنده ارسال می‌گردد.",

        "theme_title":      "تم ظاهری رابط کاربری",
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
        "welcome_title":    "欢迎使用 OXY 设置向导",
        "welcome_sub":      "自主 AI 编程智能体 · 交互式配置",
        "step":             "步骤",
        "of":               "/",
        "done_title":       "配置完成！",
        "done_body":        "配置已保存至 [cyan]{path}[/]\n随时运行 [bold cyan]python oxy.py[/] 启动体验。",

        "lang_title":       "语言选择",
        "lang_desc":        "请选择您的偏好交互语言：",

        "provider_title":   "AI 服务提供商",
        "provider_desc":    "选择您的模型托管平台：",
        "provider_hint":    "OXY 支持所有 OpenAI 兼容接口（DeepSeek, OpenAI, Groq, Ollama 等）。",

        "model_title":      "选择模型",
        "model_desc":       "选择推荐模型或输入自定义模型名称：",
        "model_custom":     "自定义模型...",
        "model_custom_desc":"手动输入其他模型标识符",

        "key_title":        "API 认证密钥",
        "key_desc":         "请输入您的 API Key：",
        "key_hint":         "密钥仅安全保存在本地 oxy_config.json，直接发送给对应服务商。",

        "theme_title":      "界面视觉主题",
        "theme_desc":       "选择您喜欢的终端外观风格：",

        "security_title":   "工具安全与执行权限",
        "security_desc":    "设置对文件修改与终端命令执行的确认策略：",

        "adv_title":        "高级推理参数",
        "adv_desc":         "是否需要微调记忆轮数与推理参数？",
        "adv_history":      "历史对话轮数",
        "adv_temperature":  "采样温度 (0.0 = 精确, 1.0 = 创意)",
        "adv_max_tokens":   "单次响应最大 token 数",
    },
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Provider & Model Catalog
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PROVIDERS = [
    {
        "name": "DeepSeek",
        "desc": "DeepSeek V3 & R1 high-speed reasoning (Best value)",
        "url": "https://api.deepseek.com/v1",
        "models": [
            ("deepseek-chat", "DeepSeek-V3 671B flagship general & coding model"),
            ("deepseek-reasoner", "DeepSeek-R1 full reasoning & thought model"),
        ],
        "default_model": "deepseek-chat",
        "env_key": "DEEPSEEK_API_KEY",
    },
    {
        "name": "OpenAI",
        "desc": "Official OpenAI API (GPT-4o, o3-mini, o1)",
        "url": "https://api.openai.com/v1",
        "models": [
            ("gpt-4o-mini", "Fast, efficient, highly intelligent default"),
            ("gpt-4o", "Flagship multimodal intelligence"),
            ("o3-mini", "Next-gen STEM & coding reasoning model"),
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
            ("llama-3.3-70b-versatile", "Flagship Llama 3.3 running on Groq LPU"),
            ("deepseek-r1-distill-llama-70b", "DeepSeek R1 reasoning on Groq LPU"),
            ("llama-3.1-8b-instant", "Ultra-fast instant coding & chat model"),
        ],
        "default_model": "llama-3.3-70b-versatile",
        "env_key": "GROQ_API_KEY",
    },
    {
        "name": "OpenRouter",
        "desc": "Unified router for Claude, GPT, DeepSeek, Mistral",
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
        "desc": "Open-source model cloud infrastructure",
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
            ("qwen2.5-coder:latest", "Recommended: Qwen 2.5 Coder specialized for programming"),
            ("llama3.1:latest", "Meta Llama 3.1 instruct model"),
            ("deepseek-r1:latest", "DeepSeek R1 distilled reasoning model"),
        ],
        "default_model": "qwen2.5-coder:latest",
        "env_key": "",
    },
    {
        "name": "Local (LM Studio)",
        "desc": "Local GUI model server (localhost:1234)",
        "url": "http://localhost:1234/v1",
        "models": [
            ("local-model", "Active model currently loaded in LM Studio GUI"),
        ],
        "default_model": "local-model",
        "env_key": "",
    },
    {
        "name": "Custom Endpoint",
        "desc": "Any custom OpenAI-compatible server URL",
        "url": "",
        "models": [],
        "default_model": "",
        "env_key": "",
    },
]

THEMES_INFO = [
    ("cyber",   "Cyber",    "Electric cyan borders, neon green badges, matrix aesthetics"),
    ("aurora",  "Aurora",   "Northern lights palette, soft violet & emerald gradients"),
    ("minimal", "Minimal",  "Clean, distraction-free monochrome for focused coding"),
]

PERMISSION_OPTIONS = [
    ("ask",  "Ask Permission (Recommended)", "Prompts confirmation before mutating files or running shell commands"),
    ("auto", "Auto-Approve (Autonomous)",   "Executes all tool operations autonomously without interactive prompts"),
]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Input Helpers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _ask_input(prompt_text: str, default: str = "", password: bool = False, theme: dict = None) -> str:
    """Prompt user for clean single-line text input."""
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
        ("English",  "Default international interface"),
        ("فارسی",    "رابط کاربری فارسی با پشتیبانی کامل و روان"),
        ("中文",      "中文交互界面与本地化说明"),
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
        console.print(f"  [bold green]✔[/] [dim]Local provider selected — no authentication key required.[/]\n")
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

    # ── Save Configuration ─────────────────────────────────────
    save_config(config)

    # ── Hermes-Style Configuration Summary Dashboard ───────────
    console.print()
    t = Table.grid(padding=(0, 2))
    t.add_column(style="bold cyan", justify="right")
    t.add_column(style="bold white")

    t.add_row("Language", lang_options[lang_idx][0])
    t.add_row("Provider", provider["name"])
    t.add_row("Endpoint", config["base_url"])
    t.add_row("Model", config["model"])
    t.add_row("API Key", _mask_key(config["api_key"]))
    t.add_row("Theme", chosen_theme_key.capitalize())
    t.add_row("Security Gate", f"[yellow]{config['permission_mode']}[/]")
    t.add_row("Tools", "[bold green]9 active tools[/] (read, write, edit, bash, glob, grep...)")
    t.add_row("Config File", CONFIG_FILE)

    console.print(Panel(
        t,
        title=f"[bold green]✔ {s['done_title']}[/]",
        subtitle="[dim]Configuration saved · Ready to code[/]",
        border_style="green",
        box=box.ROUNDED,
        padding=(1, 2),
    ))
    console.print()
    console.print(f"  [bold cyan]Launch OXY anytime with:[/] [bold white on #111b27] python3 oxy.py [/]\n")

    return config
