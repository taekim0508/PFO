"""Rewriting a question before it is embedded.

Every document in the corpus is about one person, so that person's name in a question
says nothing about which passage answers it. To an embedding model it still says a lot:
a rare name is a strong signal, and the only stored text carrying it is the title of
`about.md`, which D35 embeds with every one of that file's chunks. A question naming the
subject is pulled toward those chunks whatever it asks. Swapping the name for a pronoun
before embedding removes the pull, and leaves the question everywhere else untouched.
"""

from __future__ import annotations

import re
from collections.abc import Sequence


def neutralize_subject(query: str, names: Sequence[str]) -> str:
    """`query` with each of `names` replaced by "he", or by "his" when possessive.

    Matching ignores case and takes whole words only, so "tae" is caught and "taekim0508"
    is not. Longer names are tried first, so "Tae Kim" becomes "he" rather than "he Kim".
    Spaces inside a name match any run of whitespace.
    """
    forms = sorted({name.strip() for name in names if name.strip()}, key=len, reverse=True)
    if not forms:
        return query
    alternatives = "|".join(r"\s+".join(map(re.escape, form.split())) for form in forms)
    pattern = re.compile(rf"(?<!\w)(?:{alternatives})(?P<possessive>['’]s)?(?!\w)", re.I)
    return pattern.sub(lambda match: "his" if match.group("possessive") else "he", query)
