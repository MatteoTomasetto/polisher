"""Built-in modes. Each mode is a prompt; add your own in config.toml or a preset.

A mode can offer choices (a tone, a language...). Its prompt then contains {choice}, and the
menu opens a second step where you pick one or type your own.
"""
from __future__ import annotations

from dataclasses import dataclass


def clean_choice(value: str) -> str:
    return " ".join(str(value).split())[:60]


@dataclass(frozen=True)
class Mode:
    key: str
    label: str
    prompt: str
    hotkey: str = ""
    suggestions: int | None = None  # None -> use the general setting
    temperature: float | None = None
    choices: tuple[str, ...] = ()
    choice_label: str = ""
    default_choice: str = ""

    def default(self) -> str:
        return self.default_choice or (self.choices[0] if self.choices else "")

    def render(self, choice: str | None = None) -> str:
        """The action text sent to the model, with {choice} filled in."""
        if not self.choices:
            return self.prompt
        return self.prompt.replace("{choice}", clean_choice(choice or self.default()))


BUILTIN_MODES: dict[str, dict] = {
    "polish": {
        "label": "polish",
        "prompt": (
            "Polish the text with {choice} intensity. Preserve the author's meaning, factual "
            "claims, technical details and intended tone. Do not add new information. "
            "For light: correct grammar, spelling and punctuation, making only small edits. "
            "For medium: noticeably improve vocabulary, clarity, sentence structure, readability "
            "and flow; replace awkward or repetitive wording and restructure sentences when useful. "
            "For hard: perform a thorough rewrite, substantially improving phrasing, rhythm, "
            "structure and flow; combine or split sentences and reorganize the passage when "
            "beneficial, while preserving every important idea and the author's voice. "
            "Return only the improved text."
        ),
        "choices": ["light", "medium", "hard"],
        "choice_label": "intensity",
        "default_choice": "medium",
    },
    "rephrase": {
        "label": "rephrase",
        "prompt": (
            "Rewrite the text with different wording and sentence structure while keeping "
            "exactly the same meaning. Write it in a {choice} tone."
        ),
        "choices": ["neutral", "formal", "casual", "friendly", "confident", "persuasive",
                    "empathetic", "academic"],
        "choice_label": "tone",
        "default_choice": "neutral",
    },
    "translate": {
        "label": "translate",
        "prompt": (
            "Translate the text into {choice}. Keep the meaning, tone and formatting. "
            "Output only the translation."
        ),
        "choices": ["english", "italian", "french", "spanish", "german", "portuguese",
                    "dutch", "russian", "chinese", "japanese"],
        "choice_label": "language",
        "default_choice": "english",
        "suggestions": 1,
    },
    "compress": {
        "label": "compress",
        "prompt": (
            "Compress the text: express the same ideas and keep every key fact, but with "
            "clearly fewer words. Cut filler, repetition and wordy phrasing. Do not change "
            "the meaning."
        ),
    },
    "expand": {
        "label": "expand",
        "prompt": (
            "Make the text longer by adding something useful: more detail, a short "
            "explanation, a concrete example or a connecting idea that fits the context. "
            "Keep the original content and tone. Do not invent specific facts, numbers, "
            "names or citations."
        ),
    },
    "synonym": {
        "label": "synonym",
        "prompt": (
            "The selection is a word or short phrase. Give replacement synonyms that fit the "
            "same meaning and register. Each option must be one replacement for the whole "
            "selection, not a list. Keep capitalisation and inflection (tense, number)."
        ),
        "suggestions": 5,
    },
    "grammar": {
        "label": "fix grammar",
        "prompt": (
            "Fix only grammar, spelling and punctuation errors. Do not change wording or "
            "style in any other way."
        ),
        "suggestions": 1,
    },
    "academic": {
        "label": "academic tone",
        "prompt": (
            "Rewrite in a formal academic register suitable for a scientific paper: precise, "
            "concise and objective. Preserve all technical content, numbers and citations."
        ),
    },
}


def mode_from_dict(key: str, data: dict) -> Mode:
    if "prompt" not in data:
        raise ValueError(f"mode '{key}' needs a 'prompt'")
    choices = tuple(clean_choice(c) for c in data.get("choices", ()) if str(c).strip())
    if choices and "{choice}" not in str(data["prompt"]):
        raise ValueError(f"mode '{key}' has choices, so its prompt must contain {{choice}}")
    default = clean_choice(data.get("default_choice", "")) if choices else ""
    if default and default not in choices:
        raise ValueError(f"mode '{key}': default_choice '{default}' is not in choices")
    sugg, temp = data.get("suggestions"), data.get("temperature")
    return Mode(
        key=key,
        label=str(data.get("label", key.replace("_", " "))),
        prompt=str(data["prompt"]),
        hotkey=str(data.get("hotkey", "")),
        suggestions=int(sugg) if sugg is not None else None,
        temperature=float(temp) if temp is not None else None,
        choices=choices,
        choice_label=str(data.get("choice_label", "choose" if choices else "")),
        default_choice=default,
    )
