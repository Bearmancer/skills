# /// script
# requires-python = ">=3.12"
# ///

import re
import sys

VERIFY_WORDS = re.compile(
    r"\b(fact[- ]?check|debunk|verify (these|this|the) (claims?|statements?)|check (these|this|the) claims?|are these (claims )?(true|correct))\b",
    re.I,
)
RULES_WORDS = re.compile(
    r"\b(rulebook|rule ?book|how (do|to) (i|you|we) play|how to play|rules (for|of) \w|board ?game|boardgame|bgg|boardgamegeek|errata|player count)",
    re.I,
)
RULES_FILE = re.compile(
    r"[\w./\\-]*(rule|regel|anleitung|manual)[\w./\\ -]*\.pdf", re.I
)
LEARN_WORDS = re.compile(
    r"\b(teach me|help me understand|go through|chapter by chapter|course (on|about)|notes on|treatise|walk me through)\b",
    re.I,
)
ANSWER_WORDS = re.compile(
    r"\b(is (it|this|that) (really )?true|how true is (it|this|that)|true or false|did .{3,} (really|actually) happen)\b|\b(did|does|was|were) .{3,} really\b",
    re.I,
)
QUESTION_START = re.compile(
    r"^\s*(why|what|when|where|who|which|how|did|does|do|was|were|is|are|has|have|can|could|will|would|should)\b",
    re.I,
)
CLASSICAL_PLURALS = re.compile(
    r"\b(symphon(?:ies)|concert(?:os|i)|overtures|tone poems|string quartets|suites)\b",
    re.I,
)
CLASSICAL_WORD = re.compile(
    r"\b(symphon\w*|concert(?:o|os|i)|overtures?|tone poems?|quartets?|suites?|sonatas?|operas?|requiems?|cantatas?|orchestral|classical|composers?|beethoven|mozart|bach|brahms|tchaikovsky|shostakovich)\b",
    re.I,
)
CLASSICAL_CUES = re.compile(
    r"(bored of (beethoven|mozart|bach|brahms|tchaikovsky|the canon)|new (concerto|overture|symphony))",
    re.I,
)
CLASSICAL_HINTS = re.compile(r"(deep cuts?|haven'?t heard)", re.I)
LIST_LINE = re.compile(r"^\s*(?:[-*•]|\d{1,3}[.)])\s+\S")


def infer_mode(prompt):
    m = VERIFY_WORDS.search(prompt)
    if m:
        return "verify", f"verify word: {m.group(0)!r}"
    list_lines = [ln for ln in prompt.splitlines() if LIST_LINE.match(ln)]
    if len(list_lines) >= 3 and any(len(ln.split()) >= 5 for ln in list_lines):
        return "verify", f"pasted claim list ({len(list_lines)} items)"
    m = RULES_WORDS.search(prompt)
    if m:
        return "rules", f"rules word: {m.group(0)!r}"
    m = RULES_FILE.search(prompt)
    if m:
        return "rules", f"rulebook file: {m.group(0)!r}"
    m = ANSWER_WORDS.search(prompt)
    if m:
        return "answer", f"answer phrasing: {m.group(0)!r}"
    m = LEARN_WORDS.search(prompt)
    if m:
        return "learn", f"learn word: {m.group(0)!r}"
    question = bool(QUESTION_START.match(prompt)) or prompt.strip().endswith("?")
    m = CLASSICAL_CUES.search(prompt) or (
        None if question else CLASSICAL_PLURALS.search(prompt)
    )
    if not m and CLASSICAL_WORD.search(prompt):
        m = CLASSICAL_HINTS.search(prompt)
    if m:
        return "recommend", f"classical works wanted: {m.group(0)!r}"
    if question:
        return "answer", "question"
    return "learn", "default"


def main(argv=None):
    text = " ".join(argv if argv is not None else sys.argv[1:]) or sys.stdin.read()
    mode, reason = infer_mode(text)
    print(f"{mode}\t{reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
