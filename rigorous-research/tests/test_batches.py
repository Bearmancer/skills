from pathlib import Path

from scripts import driver


def _ask(tmp_path, name, role, step, fresh=True):
    p = tmp_path / "agent" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    head = f"role: {role}\nstep: {step}\nfresh subagent: {'yes' if fresh else 'no'}\n"
    p.write_text(head + "---\nbody\n", encoding="utf-8")
    return str(p)


def _wait(tmp_path, asks):
    state = driver.RunState(run_id="r1", topic="t", prompt="p")
    d = driver.Driver(tmp_path, state, {})
    d._wait("verify", driver.NeedsAgent(asks))
    return (tmp_path / "ASKS.md").read_text(encoding="utf-8"), Path(
        tmp_path / "batches"
    )


def test_flat_list_retained(tmp_path):
    names = [
        _ask(tmp_path, f"x{i}.ask.md", "extractor", f"verify.c1.r1.evidence.s{i:02d}")
        for i in range(3)
    ]
    asks_text, _ = _wait(tmp_path, names)
    for n in names:
        assert f"- {n}" in asks_text


def test_extractor_cap_6(tmp_path):
    names = [
        _ask(tmp_path, f"x{i}.ask.md", "extractor", f"verify.c1.r1.evidence.s{i:03d}")
        for i in range(13)
    ]
    _, batches_dir = _wait(tmp_path, names)
    batch_files = list(batches_dir.glob("extractor-*.batch.md"))
    assert len(batch_files) >= 2
    for bf in batch_files:
        asks_in = [
            l
            for l in bf.read_text(encoding="utf-8").splitlines()
            if l.strip().startswith("- ask:")
        ]
        assert len(asks_in) <= 6


def test_balanced_sizes(tmp_path):
    names = [
        _ask(tmp_path, f"x{i}.ask.md", "extractor", f"verify.c1.r1.evidence.s{i:03d}")
        for i in range(12)
    ]
    _, batches_dir = _wait(tmp_path, names)
    batch_files = sorted(batches_dir.glob("extractor-*.batch.md"), key=lambda p: p.name)
    sizes = [
        sum(
            1
            for l in p.read_text(encoding="utf-8").splitlines()
            if l.strip().startswith("- ask:")
        )
        for p in batch_files
    ]
    assert max(sizes) - min(sizes) <= 1


def test_verifier_cap_10(tmp_path):
    names = [
        _ask(tmp_path, f"v{i}.ask.md", "verifier", f"verify.c{i}.r5.positions")
        for i in range(1)
    ]
    _, batches_dir = _wait(tmp_path, names)
    batch_files = list(batches_dir.glob("verifier-*.batch.md"))
    assert len(batch_files) == 1


def test_media_cap_1(tmp_path):
    names = [_ask(tmp_path, f"m{i}.ask.md", "media", f"media.c{i}") for i in range(3)]
    _, batches_dir = _wait(tmp_path, names)
    batch_files = list(batches_dir.glob("media-*.batch.md"))
    assert len(batch_files) == 3


def test_non_fresh_not_batched(tmp_path):
    names = [
        _ask(tmp_path, f"n{i}.ask.md", "author", "write.draft", fresh=False)
        for i in range(5)
    ]
    _, batches_dir = _wait(tmp_path, names)
    assert not list(batches_dir.glob("author-*.batch.md"))


def test_order_by_step_name(tmp_path):
    names = [
        _ask(tmp_path, "z.ask.md", "extractor", "verify.c2.r1.evidence.s01"),
        _ask(tmp_path, "a.ask.md", "extractor", "verify.c1.r1.evidence.s01"),
    ]
    _, batches_dir = _wait(tmp_path, names)
    batch_files = list(batches_dir.glob("extractor-*.batch.md"))
    assert batch_files
    lines = batch_files[0].read_text(encoding="utf-8")
    pos_z = lines.index("z.ask.md")
    pos_a = lines.index("a.ask.md")
    assert pos_a < pos_z
