import re
import unicodedata


def normalize_name(name: str) -> str:
    """Lowercase, strip punctuation, remove accents, strip suffixes.

    'José Ramírez Jr.' -> 'jose ramirez'
    'C.J. Abrams' -> 'cj abrams'
    'Bobby Witt Jr.' -> 'bobby witt'
    """
    # 1. Unicode NFKD normalize, strip combining characters (removes accents)
    text = unicodedata.normalize("NFKD", name)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))

    # 2. Lowercase
    text = text.lower()

    # 3. Remove periods
    text = text.replace(".", "")

    # 4. Strip suffixes: Jr, Sr, II, III, IV (whole word, end of string)
    text = re.sub(r"\b(jr|sr|ii|iii|iv)\s*$", "", text.strip())

    # 5. Strip extra whitespace
    text = re.sub(r"\s+", " ", text).strip()

    return text
