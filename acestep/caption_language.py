"""Keep the language named in an LM caption in line with the language the user chose.

In create_sample (Simple mode) the 5Hz LM writes the caption itself and often names a singing language picked at
random: with French chosen, 7 captions out of 13 said "sung in Finnish", "Czech", "Polish", "Norwegian", "Spanish" or
"Portuguese". That caption goes to the DiT next to "# Languages: fr", which gives it two orders that contradict each
other. When a language is chosen, a language named for the singing is replaced by the chosen one.

Only phrases about the singing are touched ("sung in Polish", "a Czech vocal", "Spanish lyrics"), so "Spanish guitar",
"French horn" or "Latin percussion" stay as they are.
"""

import re

LANGUAGE_NAMES = {
    "ar": "Arabic", "az": "Azerbaijani", "bg": "Bulgarian", "bn": "Bengali", "ca": "Catalan", "cs": "Czech",
    "da": "Danish", "de": "German", "el": "Greek", "en": "English", "es": "Spanish", "fa": "Persian", "fi": "Finnish",
    "fr": "French", "he": "Hebrew", "hi": "Hindi", "hr": "Croatian", "ht": "Haitian Creole", "hu": "Hungarian",
    "id": "Indonesian", "is": "Icelandic", "it": "Italian", "ja": "Japanese", "ko": "Korean", "la": "Latin",
    "lt": "Lithuanian", "ms": "Malay", "ne": "Nepali", "nl": "Dutch", "no": "Norwegian", "pa": "Punjabi",
    "pl": "Polish", "pt": "Portuguese", "ro": "Romanian", "ru": "Russian", "sa": "Sanskrit", "sk": "Slovak",
    "sr": "Serbian", "sv": "Swedish", "sw": "Swahili", "ta": "Tamil", "te": "Telugu", "th": "Thai", "tl": "Tagalog",
    "tr": "Turkish", "uk": "Ukrainian", "ur": "Urdu", "vi": "Vietnamese", "yue": "Cantonese", "zh": "Chinese",
}
# Other names the LM uses for the same languages.
_EXTRA_NAMES = ["Mandarin", "Farsi", "Filipino", "Creole", "Brazilian Portuguese", "Castilian", "Flemish"]

_NAMES = sorted(set(LANGUAGE_NAMES.values()) | set(_EXTRA_NAMES), key=len, reverse=True)
_LANG = r"(?:" + "|".join(re.escape(n) for n in _NAMES) + r")"
_SINGING_VERBS = r"(?:sung|sings|sing|singing|sang|performed|delivered|rapped|raps|rapping|vocals?|lyrics)"
_SINGING_NOUNS = r"(?:vocals?|vocalists?|lyrics|singing|singer|lead|rap|rapping|verses?|chorus|hook|language)"

# "sung in Polish", "vocals in the Czech language", "lyrics entirely in Spanish"
_IN_LANG = re.compile(
    r"\b(" + _SINGING_VERBS + r"\b[^.,;]{0,30}?\bin\s+(?:the\s+)?)(" + _LANG + r")\b", re.IGNORECASE)
# "a Czech vocal", "Spanish lyrics", "Portuguese-language vocals", "Polish female vocal"
_LANG_NOUN = re.compile(
    r"\b(" + _LANG + r")((?:-language)?(?:\s+(?:female|male|lead|emotive|clear|soft|breathy))*\s+" + _SINGING_NOUNS + r")\b",
    re.IGNORECASE)


def language_name(code) -> str:
    if not isinstance(code, str):
        return ""
    return LANGUAGE_NAMES.get(code.strip().lower().split("-")[0], "")


def align_caption_language(caption: str, language) -> str:
    """Replace a singing language named in ``caption`` that differs from ``language`` (a code such as "fr")."""
    target = language_name(language)
    if not caption or not target:
        return caption

    def swap(name: str) -> str:
        return name if name.lower() == target.lower() else target

    caption = _IN_LANG.sub(lambda m: m.group(1) + swap(m.group(2)), caption)
    caption = _LANG_NOUN.sub(lambda m: swap(m.group(1)) + m.group(2), caption)
    return caption
