"""Repairs of lyrics written by the 5Hz LM.

French: the LM sometimes writes a line break in place of the lone token " n" (id 308 in its tokenizer), so
"elle ferait n'importe quoi" comes out as "elle ferait" / "'importe quoi". The tokenizer itself is not at fault
(it encodes " n" as 308 and decodes 308 as " n"): the slip comes from the model.
A French lyric line never starts with an elided "'importe" or "'est", so a break followed by an apostrophe
and a vowel (or h), right after a letter, is put back as " n'", unless the line opens a quoted phrase that it
closes ("Il dit" / "'au revoir'"). A missing n before a vowel ("Les" / "éons" for
"Les néons") cannot be told apart from a real line break and is left alone.
"""

import re

_FRENCH_LOST_N = re.compile(r"(?<=[^\W\d_])\n'(?=[aeiouyhàâäéèêëîïôöûüœæAEIOUYHÀÂÄÉÈÊËÎÏÔÖÛÜŒÆ])")


def is_french(language) -> bool:
    return isinstance(language, str) and language.strip().lower().split("-")[0] == "fr"


# A closing quote: an apostrophe followed by a space, punctuation or the end of the line (an elision is followed by a letter).
_CLOSING_QUOTE = re.compile(r"'(?=[\s.,;:!?)\]»]|$)")


def _repair_match(match: "re.Match") -> str:
    # "Il dit\n'au revoir'" opens a quoted phrase on the new line: it is not a lost n.
    rest = match.string[match.end():].split("\n", 1)[0]
    return match.group(0) if _CLOSING_QUOTE.search(rest) else " n'"


def repair_lm_lyrics(lyrics: str, language) -> str:
    """Return the lyrics with the known LM slips of ``language`` repaired (only French for now)."""
    if not lyrics or not is_french(language):
        return lyrics
    return _FRENCH_LOST_N.sub(_repair_match, lyrics)
