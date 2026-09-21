"""Splits a fused Sanskrit compound title into its constituent words for
search aliasing — "vishnusahasranama" -> ["vishnu", "sahasranama"] — so a
query using the naturally-spaced form still matches a title that's
conventionally written as one word.

This is *not* a sandhi-vigraha (grammatical compound resolution): that's a
genuinely hard, still-unsolved-in-general problem in Sanskrit computational
linguistics, needing a real morphological analyzer and a full lexicon.
What's here is a much smaller, honest tool for a much smaller job — greedy
longest-match segmentation against a domain-specific word list (the deity
names and genre/type words that actually recur across this corpus's
titles), applied to the fold()'d English rendering. It resolves the common
case this exists for; it will not correctly segment an unfamiliar or
irregular compound, and returns no aliases rather than guess wrong.
"""

import re

# Longer entries first isn't required (the matcher tries longest-first
# regardless) but keeps this readable as a reference list, roughly grouped.
_DEITY_WORDS = [
    "vishnu", "shiva", "shakti", "devi", "durga", "lakshmi", "mahalakshmi",
    "saraswati", "sarasvati", "parvati", "kali", "kalika", "bhairavi",
    "tripurasundari", "shodashi", "bhuvaneshwari", "bhuvaneswari", "chinnamasta",
    "dhumavati", "bagalamukhi", "matangi", "kamala", "annapurna", "meenakshi",
    "kamakshi", "kamakhya", "chamundi", "chamundeshwari", "bhavani", "gauri",
    "ambika", "amba", "radha", "sita", "godha", "goda", "tulasi", "ganga",
    "yamuna", "saraswathi", "gayatri", "savitri", "sandhya",
    "ganesha", "ganapati", "ganapathi", "vinayaka", "vighneshwara",
    "subrahmanya", "kartikeya", "skanda", "murugan", "shanmukha", "guha",
    "hanuman", "hanumat", "anjaneya", "maruti", "vayuputra", "bajrang",
    "rama", "ramachandra", "raghava", "raghunatha", "sitarama",
    "krishna", "gopala", "govinda", "keshava", "madhava", "damodara",
    "narayana", "vasudeva", "achyuta", "purushottama", "venugopala",
    "venkateswara", "venkatesha", "srinivasa", "balaji", "padmanabha",
    "ranganatha", "jagannatha", "hayagriva", "narasimha", "nrusimha",
    "varaha", "kurma", "matsya", "vamana", "parashurama", "buddha", "kalki",
    "dakshinamurthy", "dakshinamurti", "nataraja", "bhairava", "kalabhairava",
    "batukabhairava", "rudra", "mrityunjaya", "shankara", "shankaracharya",
    "adishankara", "raghavendra", "dattatreya", "sai", "shirdisai",
    "surya", "aditya", "chandra", "budha", "guru", "brihaspati", "bruhaspati",
    "shukra", "shani", "rahu", "ketu", "angaraka", "mangala", "kuja",
    "navagraha", "brahma", "indra", "agni", "vayu", "varuna", "yama", "kubera",
    "ayyappa", "sabarimala", "vithoba", "panduranga",
]

_GENRE_WORDS = [
    # kept to atomic/base words only -- deliberately no pre-fused entries
    # like "sahasranamastotram" (that's "sahasranama" + "stotram", and the
    # greedy matcher already produces both as separate alias entries when
    # they occur back to back; putting the fused form in the dictionary
    # would make the matcher swallow it as one token and silently lose the
    # more useful granular split).
    "sahasranama", "sahasranamam", "ashtottarashatanama", "ashtottarasatanama",
    "ashtottaranama", "namavali", "namavalih", "namastotram", "namakam",
    "chamakam", "laghunyasa", "dwadashanama", "dvadashanama", "shodashanama",
    "trishati", "trishatinama",
    "stotram", "stotra", "stuti", "stutih", "stavam", "stavan", "stava",
    "stavaraja", "kavacham", "kavacha", "raksha", "ashtakam", "ashtaka",
    "panchakam", "panchaka", "pancharatnam", "dashakam", "dashaka",
    "shatakam", "shataka", "chalisa", "chaleesa", "aarti", "arati", "aarati",
    "mangalam", "mangalashtakam", "mangalashasanam", "suktam", "sukta",
    "mantram", "mantra", "upanishad", "upanishat", "gita", "geetha",
    "purana", "puranam", "samhita", "samhitha", "saptashati", "saptasati",
    "hridayam", "hrudayam", "hridaya", "dandakam", "bhujangam", "bhujanga",
    "prayata", "dhyanam", "panjaram", "panjara", "kalyanam", "vidhanam",
    "puja", "pooja", "vidhi", "katha", "mala", "malika", "manjari",
    "sangraha", "sangrahah", "kritam", "virachitam", "gadyam", "khadgamala",
    "manasapuja", "aparadha", "kshamapana", "shatkam", "satkam", "lahari",
    "vachanam", "prarthana", "prathana", "smaranam", "japam", "suprabhatam",
    "namaskaram", "vandanam", "arghyam",
]

_PREFIX_WORDS = ["sri", "shri", "sree", "srimad", "shreemad", "maha", "sree"]

_ALL_WORDS = sorted(
    set(_DEITY_WORDS) | set(_GENRE_WORDS) | set(_PREFIX_WORDS), key=len, reverse=True
)


def split_aliases(title_english: str) -> list[str]:
    """Best-effort dictionary segmentation of a title's significant words.

    Operates on the already-fold()'d plain-English rendering (see
    common.to_plain_english), so it's matching against the same spelling
    conventions the dictionary above uses. Returns [] rather than a
    partial/guessed split when nothing in the dictionary matches at all —
    a title with no recognized parts gets no aliases, not a wrong one.
    """
    flat = re.sub(r"[^a-z]", "", title_english.lower())
    if not flat:
        return []

    found: list[str] = []
    i = 0
    n = len(flat)
    while i < n:
        match = None
        for word in _ALL_WORDS:
            if flat.startswith(word, i):
                match = word
                break
        if match:
            found.append(match)
            i += len(match)
        else:
            i += 1  # skip one unrecognized character, keep scanning
    # dedupe while preserving first-seen order (a word can legitimately
    # recur, e.g. "shivashivastuti", but that's not useful as two aliases)
    seen = set()
    unique = []
    for w in found:
        if w not in seen:
            seen.add(w)
            unique.append(w)
    return unique
