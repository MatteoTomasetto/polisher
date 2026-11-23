# Polisher

Polisher is a small desktop utility for editing selected text with an LLM. Select text in an application, press a global hotkey, choose an action, and Polisher pastes the result back into the original application. It is designed for browsers, email clients, Word processors, IDEs, terminals and scientific-writing tools such as Overleaf.

## Hotkeys

| Shortcut | Action |
| --- | --- |
| `Ctrl+Alt+P` | Run **medium polish** immediately (one result, no preview by default). |
| `Ctrl+Alt+M` | Open the action menu. |

The menu workflow is: **choose an action → choose its option (for example Polish → light / medium / hard) → review the result → Replace**. Press `Esc` to cancel at any stage. In the review window, use `1`, `2`, `3` to switch between suggestions, `Enter` or **Replace** to apply, and `Esc` to keep the original. Your application's undo command (`Ctrl+Z` or `Cmd+Z`) undoes the replacement.

The popup uses the system font when available (Inter or Ubuntu on Linux), a dark high-contrast palette and clearer spacing. The review panel uses larger 14 pt text and bold, high-contrast inserted/deleted text so alternatives remain readable when change highlighting is enabled. It is positioned near the mouse pointer. Status and error messages appear at that same location. A successful replacement displays “text replaced”; an unchanged result displays “no changes suggested”; errors include a reason rather than silently leaving the selection untouched.

## Actions

- **Polish** — choose light, medium or hard intensity.
  - Light: grammar, spelling and punctuation with minimal wording changes.
  - Medium: noticeably improve vocabulary, clarity, sentence structure and flow.
  - Hard: substantially rewrite and restructure while preserving meaning and technical details.
- **Rephrase** — choose a tone (neutral, formal, casual, friendly, confident, persuasive, empathetic or academic).
- **Translate** — choose a target language.
- **Compress** — express the same ideas in fewer words.
- **Expand** — add helpful explanation or detail without inventing facts.
- **Synonym** — suggest replacements for a selected word or phrase.
- **Fix grammar** — correct grammar, spelling and punctuation only.
- **Academic tone** — rewrite in a precise scientific register.

The `Ctrl+Alt+P` shortcut always uses medium polish. The menu exposes the three intensity choices and all other actions.

## Requirements

- Python 3.11 or newer.
- An LLM provider: OpenRouter, OpenAI, Anthropic, an OpenAI-compatible server, or Ollama.
- **Linux:** X11 is the best-supported desktop session. Install `python3-tk`, `xclip` and `xdotool` (`sudo apt install python3-tk xclip xdotool`). Wayland restricts global keyboard hooks and simulated clipboard shortcuts; behavior varies by compositor and desktop environment.
- **macOS:** global shortcuts and copy/paste are supported through `pynput` and the system clipboard. Grant Polisher (or the terminal used to launch it) **Accessibility** and **Input Monitoring** permissions in System Settings → Privacy & Security. The first run may require logging out/in or restarting the app after granting permissions.
- **Windows:** global shortcuts use a low-level keyboard hook and text transfer uses the Windows clipboard. No extra system packages are normally required. Some elevated/admin applications may not accept simulated paste from a non-elevated Polisher process; run both at the same privilege level if needed.

The core selection → hotkey → rewrite → paste workflow is implemented for all three operating systems, but desktop focus/permission behavior differs. Linux/X11 is the primary tested target; Windows and macOS should be smoke-tested on the specific machine. **Automatic login startup is currently installed only on Linux/XDG desktops**; on Windows/macOS, launch Polisher manually or add it to the operating system's Login Items/Startup Apps.

## Install and automatic startup

From a source checkout:

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\\Scripts\\activate
python -m pip install --upgrade pip
python -m pip install -e .
```

For development and tests:

```bash
python -m pip install -e ".[dev]"
pytest
```

On Ubuntu/Debian, install the desktop dependencies:

```bash
sudo apt install python3-tk xclip xdotool
```

After installing the package (or upgrading to a version with autostart support), run init:

```bash
polisher init
```

On Linux, `polisher init` creates the default configuration **and registers Polisher
for automatic startup at your next desktop login**. It writes a standard XDG
`.desktop` entry under `~/.config/autostart/` (or `$XDG_CONFIG_HOME/autostart/`).
You do not need to keep a terminal open. To start it immediately in the current
session, run `polisher` once; after that, future desktop logins start it automatically.
On Windows and macOS, `polisher init` creates the config but does not currently
register an OS startup task; use Startup Apps or Login Items if you want it to
launch automatically.

Manage this behavior at any time:

```bash
polisher autostart status    # check whether login startup is enabled
polisher autostart install   # enable it
polisher autostart remove    # disable it
```

To create the configuration without registering automatic startup, use
`polisher init --no-autostart`. Running `polisher init` again is safe: it keeps your existing configuration and ensures the startup entry is installed. Automatic desktop startup is currently implemented
for Linux/XDG desktops. On other operating systems, start Polisher manually.

## Configure a provider

Start by creating the configuration file:

```bash
polisher init
polisher config-path
```

The default provider is OpenRouter's free-model router. Create an API key at [openrouter.ai/keys](https://openrouter.ai/keys), then add it to the `[providers.openrouter]` section of the file printed by `polisher config-path`:

```toml
[general]
provider = "openrouter"

[providers.openrouter]
kind = "openai"
model = "openrouter/free"
base_url = "https://openrouter.ai/api/v1"
api_key = "sk-or-v1-YOUR-KEY"
```

Keep `config.toml` private; do not commit or share your API key. Alternatively, set `OPENROUTER_API_KEY` in the environment of the process that launches Polisher. If you start Polisher from a desktop launcher, it may not inherit variables exported in a terminal, so putting the key in the config file is often simpler.

`openrouter/free` dynamically routes to an available free model. The exact model can change, and free models can have rate limits or temporary availability issues. A 401 error means the key was rejected; verify it, replace it if revoked, and restart Polisher after changing configuration.

### OpenAI (paid API; ChatGPT subscription is separate)

1. Create an API key in the [OpenAI API platform](https://platform.openai.com/api-keys).
2. Check that API billing is enabled for your API account. A ChatGPT Plus/Pro subscription does **not** include API credits.
3. In the file printed by `polisher config-path`, set:

```toml
[general]
provider = "openai"

[providers.openai]
model = "gpt-4.1-mini"       # change to any model enabled for your API account
base_url = "https://api.openai.com/v1"
api_key_env = "OPENAI_API_KEY"
# Or put api_key = "sk-..." here (less secure; keep the file private)
```

Then either set `OPENAI_API_KEY` in the environment **before launching Polisher**, or put the key directly in the provider section. The environment-variable route is preferable for security, but desktop launchers do not always inherit variables exported by a terminal. On Linux/macOS, for a temporary terminal session use `export OPENAI_API_KEY="sk-..."`; in PowerShell use `$env:OPENAI_API_KEY="sk-..."`.

### Anthropic Claude (paid API; separate from Claude.ai plans)

1. Create an API key in the [Anthropic Console](https://console.anthropic.com/).
2. Ensure API billing/credits are enabled. A Claude.ai Pro/Team subscription is separate from API usage.
3. Configure the provider (the Anthropic Messages API is used directly):

```toml
[general]
provider = "anthropic"

[providers.anthropic]
model = "claude-haiku-4-5-20251001"  # fast/low-cost example; choose an active model
api_key_env = "ANTHROPIC_API_KEY"
# Or put api_key = "sk-ant-..." here (less secure; keep the file private)
```

Set `ANTHROPIC_API_KEY` in the environment before launching Polisher, or put the key in `config.toml`. Check Anthropic's [current model list and lifecycle](https://docs.anthropic.com/en/docs/about-claude/models) before selecting a model: model IDs can change and retired IDs will fail.

### Ollama (local, no API key)

Install [Ollama](https://ollama.com), download a model (for example `ollama pull llama3.1`), then set:

```toml
[general]
provider = "ollama"

[providers.ollama]
model = "llama3.1"
base_url = "http://localhost:11434"
```

Ollama keeps the selected text on your machine, assuming the model is served locally. For a hosted OpenAI-compatible endpoint, configure its `base_url`, `model`, and optional API key under a provider section with `kind = "openai"`.

### Which provider should I choose?

- **OpenRouter:** easiest way to try hosted models; free model availability and limits vary.
- **OpenAI:** direct access to OpenAI models, with usage billed to the API account.
- **Anthropic:** direct Claude API access, billed separately from Claude.ai subscriptions.
- **Ollama:** local/private, no per-request API bill; speed and quality depend on your hardware and model.

API keys are secrets. Prefer environment variables or a private config file, never commit `config.toml`, and rotate a key if it is exposed. Provider pricing and model availability can change; consult the official provider pages before choosing a model.

## Configuration reference

The main settings are in `config.toml`:

```toml
[general]
provider = "openrouter"
quick_suggestions = 1       # number of results for Ctrl+Alt+P
quick_preview = false       # true shows a review window for the quick shortcut
suggestions = 3             # number of suggestions in the menu workflow
preview = true               # show the review window after menu actions
latex_aware = "auto"        # auto | always | never
history = true

[hotkeys]
polish = "ctrl+alt+p"
menu = "ctrl+alt+m"
```

Per-application profiles can change settings based on the active window title or process name. For example, to always protect LaTeX in Overleaf:

```toml
[[profiles]]
name = "Overleaf"
match_title = "Overleaf"
latex_aware = "always"
```

## LaTeX support

When LaTeX-aware mode is enabled, commands, math, environments, citations, references and comments are temporarily hidden from the model and restored afterwards. If a suggestion drops a protected token, Polisher rejects that suggestion and retries rather than risking a damaged formula or command. Overleaf and `.tex` windows are detected automatically.

## Presets

Presets add reusable modes and per-app profiles. They cannot configure providers, API keys or destination URLs.

```bash
polisher presets list
polisher presets add presets/academic-writing.toml
polisher modes
```

The repository includes example presets for academic writing, email and translation.

## Troubleshooting

Run the diagnostic command first:

```bash
polisher doctor
```

Test the provider without the global hotkey or GUI:

```bash
polisher test "This sentence need to be improved." --mode polish --choice medium
```

Useful checks:

1. Confirm that text is selected before pressing the shortcut.
2. Confirm that the provider key is configured in the same user account that launches Polisher.
3. On Linux, use an X11 session and confirm `xclip` and `xdotool` are installed.
4. If the menu opens but the replacement does not appear, check whether the review window is waiting for **Replace** or `Enter`.
5. Check the message displayed beside the popup. Polisher reports provider errors, cancellation and unchanged suggestions there.
6. Use the application's undo shortcut if a replacement lands incorrectly.

## Commands

| Command | Purpose |
| --- | --- |
| `polisher` or `polisher run` | Start the background app. |
| `polisher init` | Create the default configuration and enable Linux login startup. |
| `polisher autostart status/install/remove` | Check, enable or disable automatic startup. |
| `polisher config-path` | Print the configuration path. |
| `polisher doctor` | Check Python dependencies, clipboard, hotkeys and configuration. |
| `polisher test "text" --mode polish --choice hard` | Test a mode from the terminal. |
| `polisher modes` | List available modes and choices. |
| `polisher history` | Show recent local edits. |
| `polisher history --restore ID` | Copy the original text of an edit back to the clipboard. |
| `polisher history --clear` | Clear local history. |

## Privacy

Selected text is sent to the provider configured by the user. Hosted providers process that text according to their own terms and privacy policies. Use Ollama for local processing. Edit history is stored locally; set `history = false` to disable it.

## Development

```bash
python -m pip install -e ".[dev]"
pytest
```

The tests cover prompt construction, provider parsing, retries, LaTeX protection, configuration, presets, history and hotkey matching. GUI focus and paste behavior should also be smoke-tested on the target operating system and desktop session.

## License

MIT
