import pytest

from scripts.infer_mode import infer_mode


@pytest.mark.parametrize(
    "prompt,mode",
    [
        ("fact-check this: the moon is 4.5 billion years old", "verify"),
        ("how do I play Ark Nova", "rules"),
        ("teach me how transformers work, chapter by chapter", "learn"),
        (
            "is it true that Irish people are genetically predisposed to alcoholism",
            "answer",
        ),
        ("did the Sony deal really close in 1988", "answer"),
        ("I'm bored of Beethoven, give me Soviet symphonies", "recommend"),
        ("why do wifi printers drop off the network", "answer"),
        ("is it true that this study shows coffee stunts growth", "answer"),
    ],
)
def test_mode_routing_matches_the_skill_table(prompt, mode):
    assert infer_mode(prompt)[0] == mode
