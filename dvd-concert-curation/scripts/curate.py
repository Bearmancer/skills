"""Curate a concert disc folder into one verified MKV per work.

uv run --quiet curate.py plan   <folder> [--out manifest.json] [--dest DIR] [--research overrides.json]
uv run --quiet curate.py plan   <folder> --strategy b --manifest approved-A.json [--research overrides.json] --out B.json
uv run --quiet curate.py merge  <folder> --manifest approved.json --out-dir DIR --approved-by "<owner ruling>"
uv run --quiet curate.py verify <folder> --manifest approved.json --out-dir DIR

Strategy A appends per-movement rips; strategy B cuts ranges out of kept whole-title
rips. Shape is auto-detected; --strategy a|b overrides. The workflow, strategy-B proof
contract and command list are documented in SKILL.md and
../references/verification.md; naming rules live in
../references/naming-and-chapters.md. The seam never deletes, moves or renames a source
and never edits tags.json.
"""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.sax.saxutils import escape

MAX_PATH = 240
CACHE_DIR = None
MOVEMENT_RX = re.compile(r"^(?:T(\d{2})-(\d{2})|(\d{2})) - ")
TITLE_RX = re.compile(r"^title (\d+)\.mkv$", re.I)
LEADING_KINDS = {"intro", "title card", "bumper", "credits"}
TRAILING_KINDS = {"applause", "encore"}
STANDALONE_KINDS = {"talk", "interview"}
DROPPED_KINDS = {"trailer"}
RESERVED = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)}
OPUS_RX = re.compile(r"\s*,?\s*\b(?:Op\.|K\.|KV|D\.|BWV|Hob\.|WoO|TrV|AV|Anh\.|WAB)\s*\d+(?:\s*(?:No\.|Nr\.)\s*\d+)?")


def run(args, check=False):
    p = subprocess.run([str(a) for a in args], capture_output=True)
    text = (p.stdout + p.stderr).decode("utf-8", "replace").lstrip("﻿")
    if check and p.returncode >= 2:
        raise RuntimeError(f"{Path(str(args[0])).name} exit {p.returncode}: {text[-800:]}")
    return p.returncode, text


def run_out(args):
    p = subprocess.run([str(a) for a in args], capture_output=True)
    return p.returncode, p.stdout.decode("utf-8", "replace").lstrip("﻿")


def norm(text):
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def clean(value):
    return str(value or "").strip()


def cache_file(kind, path):
    st = path.stat()
    key = hashlib.sha1(f"{path}|{st.st_size}|{st.st_mtime_ns}".encode("utf-8")).hexdigest()[:16]
    return CACHE_DIR / f"{kind}-{key}.json", st


def cache_load(kind, path):
    if not CACHE_DIR:
        return None
    cp, st = cache_file(kind, path)
    if cp.exists():
        d = json.loads(cp.read_text(encoding="utf-8"))
        if d.get("size") == st.st_size and d.get("mtime") == st.st_mtime_ns:
            return d
    return None


def cache_store(kind, path, payload):
    if not CACHE_DIR:
        return
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cp, st = cache_file(kind, path)
    cp.write_text(json.dumps({"size": st.st_size, "mtime": st.st_mtime_ns, **payload}), encoding="utf-8")


# ---------- research ----------

def load_research(folder, research_path):
    tags = json.loads((folder / "tags.json").read_text(encoding="utf-8-sig"))
    overrides = json.loads(Path(research_path).read_text(encoding="utf-8-sig")) if research_path else {}
    titles = []
    for t in tags.get("titles", []):
        chapters = []
        for c in t.get("chapters", []):
            c = dict(c)
            key = f'{t["title_file"]}|{c["chapter"]}'
            if key in overrides:
                c.update(overrides[key])
                c["ownerResearch"] = True
            c["kind"] = clean(c.get("kind")).lower() or "music"
            chapters.append(c)
        m = TITLE_RX.match(t.get("title_file", ""))
        titles.append({"titleFile": t["title_file"], "number": int(m.group(1)) if m else None, "chapters": chapters})
    return tags, titles


def chapter_label(c):
    num, mv = clean(c.get("movement_number")), clean(c.get("movement"))
    if c["kind"] != "music":
        return mv or c["kind"].capitalize()
    if num and mv:
        return f"{num}{' ' if num.endswith('.') else '. '}{mv}"
    return mv or None


# ---------- shape + join ----------

def detect_shape(folder):
    mkvs = sorted(p.name for p in folder.glob("*.mkv"))
    movement = [n for n in mkvs if MOVEMENT_RX.match(n)]
    if movement:
        return "movement-rips", movement
    if mkvs:
        return "whole-title", []
    return "empty", []


def join_source(name, titles):
    m = MOVEMENT_RX.match(name)
    tt, cc = (int(m.group(1)), int(m.group(2))) if m.group(1) else (None, int(m.group(3)))
    if tt is not None:
        hits = [t for t in titles if t["number"] == tt]
    else:
        hits = [t for t in titles if any(int(c["chapter"]) == cc for c in t["chapters"])]
    if len(hits) != 1:
        return None, f"{len(hits)} tags titles match {'title ' + str(tt) if tt is not None else 'bare chapter ' + str(cc)}"
    ch = [c for c in hits[0]["chapters"] if int(c["chapter"]) == cc]
    if len(ch) != 1:
        return None, f"no tags chapter {cc} in {hits[0]['titleFile']}"
    return (hits[0], ch[0]), None


# ---------- naming ----------

def possessive(c):
    display = clean(c.get("composer_display"))
    if display:
        return display.split()[-1] + "'s"
    return clean(c.get("composer")).split(",")[0].strip() + "'s"


def join_performers(names):
    return " and ".join(names) if len(names) == 2 else ", ".join(names)


def sanitize(name):
    out, open_quote = [], True
    for ch in name:
        if ch == '"':
            out.append("“" if open_quote else "”")
            open_quote = not open_quote
        elif ch == ":":
            out.append("꞉")
        else:
            out.append(ch)
    return "".join(out)


def fit_name(name, dirs, orchestra):
    def fits(n):
        return all(len(str(d / n)) <= MAX_PATH for d in dirs)

    if fits(name):
        return name, []
    steps = []
    m = re.match(r"^(.*)( \(\d{4}\)\.mkv)$", name)
    core, tail = (m.group(1), m.group(2)) if m else (name[:-4], ".mkv")
    head, _, credits = core.partition(" - ")
    pm = re.match(r"^(\S+'s)\s+(.*)$", head)
    prefix, work = (pm.group(1) + " ", pm.group(2)) if pm else ("", head)

    def build():
        return " - ".join(x for x in (prefix + work, credits) if x) + tail

    work2 = OPUS_RX.sub("", work)
    if work2 != work:
        steps.append(f"opus/catalogue dropped: '{work}' -> '{work2}'")
        work = work2
    if fits(build()):
        return build(), steps
    credits2 = credits
    if orchestra and orchestra in credits:
        for pat in (f" and {orchestra}", f"{orchestra} and ", f", {orchestra}", f"{orchestra}, ", orchestra):
            credits2 = credits2.replace(pat, "")
    elif ", " in credits:
        credits2 = credits.rsplit(", ", 1)[0]
    elif " and " in credits:
        credits2 = credits.rsplit(" and ", 1)[0]
    if credits2 != credits:
        steps.append(f"orchestra dropped: '{credits}' -> '{credits2.strip(' ,')}'")
        credits = credits2.strip(" ,")
    if fits(build()):
        return build(), steps
    budget = MAX_PATH - max(len(str(d / (prefix + " - " + credits + tail))) for d in dirs) - 3
    if budget < 1:
        raise SystemExit(f"cannot fit {MAX_PATH} chars: {name}")
    cut = work[:budget]
    cut = cut[: cut.rfind(" ")] if " " in cut else cut
    steps.append(f"work truncated: '{work}' -> '{cut}'")
    work = cut
    if not fits(build()):
        raise SystemExit(f"still over {MAX_PATH} chars: {build()}")
    return build(), steps


def name_violations(o, dirs):
    bad, name, stem = [], o["outputName"], o["mkvTitle"]
    if re.search(r'[<>:"/\\|?*\x00-\x1f]', name):
        bad.append("illegal character")
    if stem.endswith((".", " ")):
        bad.append("trailing dot/space")
    if stem.upper() in RESERVED or stem.split(".")[0].upper() in RESERVED:
        bad.append("reserved device name")
    if name != stem + ".mkv":
        bad.append("name != title + .mkv")
    for d in dirs:
        if len(str(d / name)) > MAX_PATH:
            bad.append(f"path > {MAX_PATH} under {d}")
    if any(re.search(r"[\x00-\x1f]", s["chapterName"]) for s in o["sources"]):
        bad.append("control character in a chapter name")
    return bad


# ---------- plan ----------

def probe_header(path):
    code, text = run_out(["mkvmerge", "-J", path])
    if code != 0:
        raise RuntimeError(f"mkvmerge -J exit {code} on {path}")
    j = json.loads(text)
    return {
        "seconds": round(j["container"]["properties"].get("duration", 0) / 1e9, 3),
        "tracks": [f'{t["type"]}:{t["codec"]}' for t in j["tracks"]],
        "chapterEntries": sum(c.get("num_entries", 0) for c in j.get("chapters", [])),
        "bytes": path.stat().st_size,
    }


def build_group(members, folder, dirs):
    music = [m for m in members if m["chapter"]["kind"] == "music"]
    first = music[0]["chapter"]
    flags = []

    def unique(field):
        vals = []
        for m in music:
            v = clean(m["chapter"].get(field))
            if v and v not in vals:
                vals.append(v)
        if len(vals) > 1:
            flags.append(f"inconsistent:{field}")
        return vals

    soloists = []
    for m in music:
        for s in m["chapter"].get("soloists") or []:
            if clean(s) and clean(s) not in soloists:
                soloists.append(clean(s))
    conductor, orchestra, year = unique("conductor"), unique("orchestra"), unique("performance_year")
    performers = []
    for p in soloists + conductor[:1] + orchestra[:1]:
        if p not in performers:
            performers.append(p)
    if not performers:
        flags.append("unknownPerformers")
    if not year:
        flags.append("missingYear")
    work = clean(first.get("work"))
    name = f"{possessive(first)} {work}"
    if performers:
        name += f" - {join_performers(performers)}"
    if year:
        name += f" ({year[0]})"
    name, steps = fit_name(sanitize(name) + ".mkv", dirs, orchestra[0] if orchestra else "")
    if steps:
        flags.append("nameShortened")
    sources = []
    for m in members:
        c = m["chapter"]
        label = chapter_label(c)
        if label is None:
            label = f'{c["chapter"]}. {work}'
            flags.append("fallbackChapterName")
        sources.append({
            "file": m["file"], "titleFile": m["title"]["titleFile"], "chapter": int(c["chapter"]),
            "kind": c["kind"], "role": m["role"], "chapterName": label,
            "tagsSeconds": c.get("seconds"), "confidence": c.get("confidence"),
            "ownerResearch": bool(c.get("ownerResearch")), **m["probe"],
        })
    ripped = {(s["titleFile"], s["chapter"]) for s in sources}
    missing = []
    for c in members[0]["title"]["chapters"]:
        if c["kind"] == "music" and norm(c.get("work")) == norm(work) and (members[0]["title"]["titleFile"], int(c["chapter"])) not in ripped:
            missing.append({"number": clean(c.get("movement_number")), "name": clean(c.get("movement")), "seconds": c.get("seconds"), "reason": "never ripped"})
    for m in members:
        for ms in m["chapter"].get("mergedSections") or []:
            missing.append({"number": ms.get("number"), "name": ms.get("name"), "seconds": None, "reason": "merged into adjacent chapter"})
    nums = [clean(m["chapter"].get("movement_number")) for m in music]
    if all(n.isdigit() for n in nums) and sorted(int(n) for n in nums) != list(range(1, len(nums) + 1)):
        flags.append("incomplete")
    if any(s["confidence"] == "low" for s in sources):
        flags.append("lowConfidence")
    return {
        "outputName": name, "mkvTitle": name[:-4], "composer": clean(first.get("composer_display") or first.get("composer")),
        "work": work, "soloists": soloists, "conductor": conductor[0] if conductor else None,
        "orchestra": orchestra[0] if orchestra else None, "year": year[0] if year else None,
        "venue": clean(first.get("venue")) or None, "performanceDate": clean(first.get("performance_date")) or None,
        "flags": sorted(set(flags)), "nameShorteningSteps": steps, "missingChapters": missing,
        "expectedSeconds": round(sum(s["seconds"] for s in sources), 3),
        "expectedTagsSeconds": round(sum(float(s["tagsSeconds"] or 0) for s in sources), 3),
        "sourceBytes": sum(s["bytes"] for s in sources), "sources": sources,
    }


def make_plan(folder, dest, research):
    shape, movement = detect_shape(folder)
    if shape != "movement-rips":
        raise SystemExit(f"shape '{shape}': only movement-rip folders are curated by this build (whole-title cuts are EPIC 1.1.2)")
    tags, titles = load_research(folder, research)
    joined, unclassified = {}, []
    for name in movement:
        hit, why = join_source(name, titles)
        if hit:
            joined[(hit[0]["titleFile"], int(hit[1]["chapter"]))] = name
        else:
            unclassified.append({"file": name, "reason": why})
    dirs = [dest]
    outputs, standalones, coverage = [], [], []
    for t in titles:
        chs = t["chapters"]
        order = []
        for c in chs:
            if c["kind"] == "music":
                key = (norm(c.get("composer_display") or c.get("composer")), norm(c.get("work")))
                if key not in order:
                    order.append(key)
        keyed = [(norm(c.get("composer_display") or c.get("composer")), norm(c.get("work"))) if c["kind"] == "music" else None for c in chs]
        members = {k: [] for k in order}
        for i, c in enumerate(chs):
            n = int(c["chapter"])
            file = joined.get((t["titleFile"], n))
            target, role = None, "movement"
            if c["kind"] == "music":
                target = keyed[i]
            elif c["kind"] in DROPPED_KINDS:
                role = "dropped"
            elif c["kind"] in STANDALONE_KINDS:
                role = "standalone"
            else:
                after = next((keyed[j] for j in range(i + 1, len(chs)) if keyed[j]), None)
                before = next((keyed[j] for j in range(i - 1, -1, -1) if keyed[j]), None)
                if c["kind"] in TRAILING_KINDS:
                    target, role = (before, "trailing") if before else (after, "leading")
                else:
                    target, role = (after, "leading") if after else (before, "trailing")
                if target is None:
                    role = "standalone"
            disposition = "not ripped" if file is None else role
            coverage.append({"titleFile": t["titleFile"], "chapter": n, "kind": c["kind"], "seconds": c.get("seconds"), "file": file, "disposition": disposition, "output": None})
            if file is None or role == "dropped":
                continue
            m = {"file": file, "title": t, "chapter": c, "role": role, "probe": probe_header(folder / file)}
            if role == "standalone":
                standalones.append(m)
            else:
                members[target].append(m)
        for k in order:
            ms = members[k]
            if not any(m["chapter"]["kind"] == "music" for m in ms):
                continue
            lead = [m for m in ms if m["role"] == "leading"]
            body = [m for m in ms if m["role"] == "movement"]
            trail = [m for m in ms if m["role"] == "trailing"]
            out = build_group(lead + body + trail, folder, dirs)
            for s in out["sources"]:
                for row in coverage:
                    if row["file"] == s["file"]:
                        row["output"] = out["outputName"]
            outputs.append(out)
    for m in standalones:
        c = m["chapter"]
        subject = clean(c.get("movement")) or clean(c.get("work")) or c["kind"]
        people = [p for p in (c.get("soloists") or []) + [c.get("conductor"), c.get("orchestra")] if clean(p)]
        name = subject + (f" - {join_performers(people)}" if people else "") + (f' ({clean(c.get("performance_year"))})' if clean(c.get("performance_year")) else "")
        name, steps = fit_name(sanitize(name) + ".mkv", dirs, clean(c.get("orchestra")))
        out = {"outputName": name, "mkvTitle": name[:-4], "standalone": True, "flags": ["standaloneExtra"], "nameShorteningSteps": steps,
               "missingChapters": [], "sources": [{"file": m["file"], "titleFile": m["title"]["titleFile"], "chapter": int(c["chapter"]), "kind": c["kind"],
                                                    "role": "standalone", "chapterName": subject, "tagsSeconds": c.get("seconds"), **m["probe"]}]}
        out["expectedSeconds"] = out["sources"][0]["seconds"]
        out["sourceBytes"] = out["sources"][0]["bytes"]
        for row in coverage:
            if row["file"] == m["file"]:
                row["output"] = name
        outputs.append(out)
    assigned = [s["file"] for o in outputs for s in o["sources"]] + [u["file"] for u in unclassified]
    census_ok = sorted(assigned) == sorted(movement)
    names = [o["outputName"] for o in outputs]
    violations = {o["outputName"]: name_violations(o, dirs) for o in outputs}
    violations = {k: v for k, v in violations.items() if v}
    if len(set(names)) != len(names):
        violations["(names)"] = ["duplicate output names"]
    return {
        "folder": str(folder), "dest": str(dest), "shape": shape,
        "tagsJsonSha256": hashlib.sha256((folder / "tags.json").read_bytes()).hexdigest(),
        "research": str(research) if research else None,
        "outputs": outputs, "unclassified": unclassified, "coverage": coverage,
        "census": {"movementFiles": len(movement), "assigned": len(assigned), "ok": census_ok},
        "violations": violations,
    }


def print_plan(plan):
    print(f"folder: {plan['folder']}\nshape: {plan['shape']}  census: {plan['census']}")
    for i, o in enumerate(plan["outputs"], 1):
        print(f"\n[{i}] {o['outputName']}")
        print(f"    segment title = global TITLE = {o['mkvTitle']}")
        print(f"    expected {o['expectedSeconds']} s (source headers), tags {o.get('expectedTagsSeconds')} s, {o['sourceBytes']:,} B; flags {o['flags'] or 'none'}")
        for j, s in enumerate(o["sources"], 1):
            print(f"    {j}. {s['chapterName']}  <-  {s['file']}  [{s['titleFile']} ch {s['chapter']}, {s['role']}, {s['seconds']} s]")
        for mc in o["missingChapters"]:
            print(f"    missing: {mc}")
    for row in plan["coverage"]:
        if row["output"] is None:
            print(f"coverage: {row['titleFile']} ch {row['chapter']} {row['kind']} {row['seconds']} s -> {row['disposition']} (content only in the kept title rip)")
    for u in plan["unclassified"]:
        print(f"UNCLASSIFIED: {u}")
    for k, v in plan["violations"].items():
        print(f"VIOLATION: {k}: {v}")


# ---------- strategy B: whole-title chapter cuts ----------

def parse_time(t):
    h, m, s = t.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def fmt_time(sec):
    return f"{int(sec // 3600):02d}:{int(sec % 3600 // 60):02d}:{sec % 60:012.9f}"


def title_atoms(path):
    code, xml = run_out(["mkvextract", "chapters", path])
    if code >= 2:
        raise RuntimeError(f"mkvextract chapters exit {code} on {path}")
    atoms = []
    for a in ET.fromstring(xml).iter("ChapterAtom"):
        st = a.find("ChapterTimeStart")
        if st is None:
            continue
        en = a.find("ChapterTimeEnd")
        atoms.append({"start": parse_time(st.text), "end": parse_time(en.text) if en is not None else None})
    return atoms


def video_packet_index(path):
    cached = cache_load("pktindex", path)
    if cached:
        return [tuple(p) for p in cached["packets"]]
    for attempt in range(3):
        code, text = run_out(["ffprobe", "-v", "error", "-select_streams", "v:0",
                              "-show_entries", "packet=pts_time,flags,size", "-of", "json", path])
        if code == 0:
            break
        time.sleep(5 * (attempt + 1))
    if code != 0:
        raise RuntimeError(f"ffprobe packet scan failed on {path}")
    pkts = [(float(p["pts_time"]), "K" in p.get("flags", ""), int(p["size"]))
            for p in json.loads(text)["packets"] if p.get("pts_time") not in (None, "N/A")]
    if not pkts:
        raise RuntimeError(f"no video packets on {path}")
    cache_store("pktindex", path, {"packets": pkts})
    return pkts


def audio_stream(path):
    code, text = run_out(["ffprobe", "-v", "error", "-select_streams", "a:0",
                          "-show_entries", "stream=codec_name,sample_rate,channels,bits_per_raw_sample,bits_per_sample,bit_rate", "-of", "json", path])
    if code != 0:
        raise RuntimeError(f"ffprobe audio properties exit {code} on {path}")
    streams = json.loads(text).get("streams") or []
    if not streams:
        raise RuntimeError(f"no audio stream on {path}")
    return streams[0]


def audio_bps_of(s):
    """(audio bytes/sec, size-truth label): sample rate x channels x bit depth when known,
    else the CBR stream bit_rate / 8 (AC3/DTS/MP2 discs carry no bit depth)."""
    bits = s.get("bits_per_raw_sample") or s.get("bits_per_sample")
    if not bits:
        m = re.search(r"s(\d+)", s.get("codec_name", ""))
        bits = m.group(1) if m else None
    if bits:
        return int(s["sample_rate"]) * int(s["channels"]) * int(bits) / 8, "constant-BPS audio"
    rate = s.get("bit_rate")
    try:
        rate = int(rate)
    except (TypeError, ValueError):
        rate = 0
    if rate:
        return rate / 8, "CBR audio at stream bit_rate/8"
    return None, None


def audio_bps(path):
    bps, _ = audio_bps_of(audio_stream(path))
    if bps is None:
        raise RuntimeError(f"cannot determine audio bit depth or stream bit rate on {path}")
    return bps


def plan_b(folder, approved_path, research, dest):
    approved_path = Path(approved_path)
    approved = json.loads(approved_path.read_text(encoding="utf-8"))
    if approved.get("strategy") == "b":
        raise SystemExit("plan --strategy b takes the approved strategy-A manifest, not a B manifest")
    tags, titles = load_research(folder, research)
    by_file = {t["titleFile"]: t for t in titles}
    atoms_cache, pkts_cache, header_cache = {}, {}, {}
    outputs, covered = [], {}
    for o in approved["outputs"]:
        srcs = o["sources"]
        tfs = {s["titleFile"] for s in srcs}
        if len(tfs) != 1:
            raise SystemExit(f"strategy B gap: {o['outputName']} spans titles {sorted(tfs)}; one cut cannot span rips")
        tf = srcs[0]["titleFile"]
        rip = folder / tf
        if not rip.exists():
            raise SystemExit(f"strategy B gap: title rip missing: {rip}")
        nums = [int(s["chapter"]) for s in srcs]
        if nums != list(range(nums[0], nums[0] + len(nums))):
            raise SystemExit(f"strategy B gap: {o['outputName']} chapters {nums} not contiguous in {tf}; unmapped content would fall inside the cut")
        t = by_file.get(tf)
        if t is None:
            raise SystemExit(f"strategy B gap: {tf} not in tags.json")
        if tf not in atoms_cache:
            atoms_cache[tf] = title_atoms(rip)
            header_cache[tf] = probe_header(rip)
            pkts_cache[tf] = video_packet_index(rip)
        atoms = atoms_cache[tf]
        if len(atoms) != len(t["chapters"]):
            raise SystemExit(f"strategy B gap: {tf} has {len(atoms)} chapter atoms vs {len(t['chapters'])} tags chapters")
        for i, (c, a) in enumerate(zip(t["chapters"], atoms)):
            end = a["end"] if a["end"] is not None else (atoms[i + 1]["start"] if i + 1 < len(atoms) else header_cache[tf]["seconds"])
            tags_sec = float(c.get("seconds") or 0)
            if abs((end - a["start"]) - tags_sec) > max(2.0, 0.01 * tags_sec):
                raise SystemExit(f"strategy B gap: {tf} ch {c['chapter']} atom duration {end - a['start']:.3f} s vs tags {tags_sec:.3f} s; chapter mapping cannot be trusted")
        nominal_start = atoms[nums[0] - 1]["start"]
        last = atoms[nums[-1] - 1]
        nominal_end = last["end"] if last["end"] is not None else header_cache[tf]["seconds"]
        pkts = pkts_cache[tf]
        keys = [p for p, k, _ in pkts if k and p <= nominal_start + 1e-6]
        if not keys:
            raise SystemExit(f"strategy B gap: no keyframe at/before {nominal_start:.3f} s in {tf}")
        cut_start = max(keys)
        range_video_bytes = sum(sz for p, _, sz in pkts if cut_start <= p < nominal_end)
        abps = audio_bps(rip)
        exp_sec = nominal_end - cut_start
        out = dict(o)
        out["strategy"] = "b"
        out["cut"] = {"titleFile": tf, "nominalStart": round(nominal_start, 6), "cutStart": round(cut_start, 6),
                      "cutEnd": round(nominal_end, 6), "keyframeBackoffSec": round(nominal_start - cut_start, 3),
                      "chapterTimes": [0.0] + [round(atoms[n - 1]["start"] - cut_start, 6) for n in nums[1:]],
                      "rangeVideoBytes": range_video_bytes, "audioBps": abps,
                      "expectedSeconds": round(exp_sec, 3), "expectedBytes": int(range_video_bytes + abps * exp_sec)}
        out["expectedSeconds"] = round(exp_sec, 3)
        out["sourceBytes"] = out["cut"]["expectedBytes"]
        outputs.append(out)
        for n in nums:
            covered[(tf, n)] = o["outputName"]
    coverage = []
    for t in titles:
        rip = folder / t["titleFile"]
        for c in t["chapters"]:
            n = int(c["chapter"])
            out_name = covered.get((t["titleFile"], n))
            disposition = "cut" if out_name else ("kept title rip" if rip.exists() else "UNCOVERED")
            coverage.append({"titleFile": t["titleFile"], "chapter": n, "kind": c["kind"], "seconds": c.get("seconds"),
                             "disposition": disposition, "output": out_name})
    in_cuts = sum(1 for r in coverage if r["disposition"] == "cut")
    kept = sum(1 for r in coverage if r["disposition"] == "kept title rip")
    uncov = [r for r in coverage if r["disposition"] == "UNCOVERED"]
    census = {"titleRips": len(atoms_cache), "chapters": len(coverage), "inCuts": in_cuts, "keptInRips": kept,
              "ok": not uncov and all((folder / tf).exists() for tf in atoms_cache)}
    violations = {}
    for o in outputs:
        bad = name_violations(o, [dest])
        if o["cut"]["keyframeBackoffSec"] > max(2.0, 0.05 * o["expectedSeconds"]):
            bad.append(f"keyframe backoff {o['cut']['keyframeBackoffSec']} s beyond cut tolerance")
        if bad:
            violations[o["outputName"]] = bad
    if len({o["outputName"] for o in outputs}) != len(outputs):
        violations["(names)"] = ["duplicate output names"]
    return {"folder": str(folder), "dest": str(dest), "shape": "whole-title", "strategy": "b",
            "tagsJsonSha256": hashlib.sha256((folder / "tags.json").read_bytes()).hexdigest(),
            "research": str(research) if research else None,
            "approvedManifest": str(approved_path),
            "approvedManifestSha256": hashlib.sha256(approved_path.read_bytes()).hexdigest(),
            "outputs": outputs, "unclassified": [], "coverage": coverage, "census": census, "violations": violations}


def cut_output(o, folder, path, work):
    cut = o["cut"]
    rip = folder / cut["titleFile"]
    args = ["ffmpeg", "-v", "error", "-ss", f"{cut['cutStart']:.6f}", "-to", f"{cut['cutEnd']:.6f}",
            "-i", rip, "-map", "0", "-c", "copy", "-avoid_negative_ts", "make_zero", path]
    code, text = run(args)
    if code >= 2:
        raise RuntimeError(f"ffmpeg cut exit {code}: {text[-800:]}")
    atoms = []
    for t, s in zip(cut["chapterTimes"], o["sources"]):
        atoms.append(f"    <ChapterAtom>\n      <ChapterTimeStart>{fmt_time(t)}</ChapterTimeStart>\n"
                     f"      <ChapterDisplay>\n        <ChapterString>{escape(s['chapterName'])}</ChapterString>\n"
                     "      </ChapterDisplay>\n    </ChapterAtom>")
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n<Chapters>\n  <EditionEntry>\n' + "\n".join(atoms) + "\n  </EditionEntry>\n</Chapters>\n"
    tmp = work / "chapters-tmp.xml"
    tmp.write_text(xml, encoding="utf-8")
    try:
        chap_code, _ = run(["mkvpropedit", path, "--chapters", tmp], check=True)
    finally:
        tmp.unlink(missing_ok=True)
    title_code, _ = write_title(path, o["mkvTitle"], work)
    return {"ffmpegExit": code, "cutOutput": text, "chaptersPropeditExit": chap_code, "titlePropeditExit": title_code}


def video_seconds_tail(path):
    _, jt = run_out(["mkvmerge", "-J", path])
    dur = json.loads(jt)["container"]["properties"].get("duration", 0) / 1e9
    seek = max(0.0, dur - 5.0)
    code, text = run_out(["ffprobe", "-v", "error", "-read_intervals", f"{seek:.3f}", "-select_streams", "v:0",
                          "-show_entries", "packet=pts_time,duration_time", "-of", "csv=p=0", path])
    best = None
    if code == 0:
        for line in text.splitlines():
            parts = line.strip().split(",")
            if not parts[0] or parts[0] == "N/A":
                continue
            end = float(parts[0]) + (float(parts[1]) if len(parts) > 1 and parts[1] not in ("", "N/A") else 0.0)
            best = end if best is None or end > best else best
    if best is None or abs(best - dur) > 0.5:
        return video_seconds(path), "video-stream-packets-full-scan"
    return best, "video-stream-packets-tail-seek"


def verify_output_b(o, folder, path, cut_exit):
    cut = o["cut"]
    rip = folder / cut["titleFile"]
    approved = folder / o["outputName"]
    if not approved.exists():
        raise RuntimeError(f"approved merged output missing from folder: {approved}; strategy B must prove the match")
    out_sec = video_seconds(path)
    ref_sec, ref_metric = video_seconds_tail(approved)
    range_sec = cut["expectedSeconds"]
    tol_cut = max(2.0, 0.05 * range_sec)
    tol_match = max(2.0, 0.01 * ref_sec)
    _, cj = run_out(["ffprobe", "-v", "error", "-show_chapters", "-of", "json", path])
    got = [c.get("tags", {}).get("title", "") for c in json.loads(cj).get("chapters", [])]
    want = [s["chapterName"] for s in o["sources"]]
    _, aj = run_out(["ffprobe", "-v", "error", "-show_chapters", "-of", "json", approved])
    approved_chapters = [c.get("tags", {}).get("title", "") for c in json.loads(aj).get("chapters", [])]
    expected_bytes = cut["expectedBytes"]
    out_bytes = path.stat().st_size
    size_pct = (out_bytes - expected_bytes) / expected_bytes * 100
    _, audio_truth = audio_bps_of(audio_stream(rip))
    dec_code, dec_text = run(["ffmpeg", "-v", "error", "-xerror", "-i", path, "-map", "0:v", "-map", "0:a", "-f", "null", "-"])
    _, jt = run_out(["mkvmerge", "-J", path])
    segment = json.loads(jt)["container"]["properties"].get("title")
    gtitle = global_title(path)
    _, jat = run_out(["mkvmerge", "-J", approved])
    asegment = json.loads(jat)["container"]["properties"].get("title")
    aglobal = global_title(approved)
    checks = {
        "cut": {"exit": cut_exit, "pass": cut_exit is not None and cut_exit < 2},
        "chapters": {"expected": want, "actual": got, "pass": got == want},
        "duration": {"metric": "video-stream-packets", "rangeSec": range_sec, "outputSec": round(out_sec, 3),
                     "deltaVsRangeSec": round(out_sec - range_sec, 3), "cutToleranceSec": round(tol_cut, 3),
                     "approvedSec": round(ref_sec, 3), "approvedMetric": ref_metric, "deltaVsApprovedSec": round(out_sec - ref_sec, 3),
                     "matchToleranceSec": round(tol_match, 3),
                     "pass": abs(out_sec - range_sec) <= tol_cut and abs(out_sec - ref_sec) <= tol_match},
        "codecs": {"input": streams(rip), "output": streams(path), "pass": streams(path) == streams(rip)},
        "size": {"truth": f"source-range video packet bytes + {audio_truth}", "expectedBytes": expected_bytes,
                 "outputBytes": out_bytes, "deltaPct": round(size_pct, 4), "bandPct": 2.0, "pass": abs(size_pct) <= 2.0},
        "decode": {"exit": dec_code, "messages": dec_text.splitlines()[:40], "pass": dec_code == 0},
        "title": {"expected": o["mkvTitle"], "segment": segment, "global": gtitle, "stem": path.stem,
                  "pass": segment == gtitle == path.stem == o["mkvTitle"]},
    }
    comparison = {"approvedFile": approved.name, "nameMatch": approved.name == path.name,
                  "chaptersMatch": approved_chapters == got, "approvedChapters": approved_chapters,
                  "durationDeltaSec": round(out_sec - ref_sec, 3),
                  "segmentBytesMatch": (asegment or "").encode("utf-8") == (segment or "").encode("utf-8"),
                  "globalBytesMatch": (aglobal or "").encode("utf-8") == (gtitle or "").encode("utf-8"),
                  "approvedBytes": approved.stat().st_size, "cutBytes": out_bytes}
    return checks, all(c["pass"] for c in checks.values()), comparison


def print_plan_b(plan):
    print(f"folder: {plan['folder']}\nshape: {plan['shape']}  strategy: b  census: {plan['census']}")
    for i, o in enumerate(plan["outputs"], 1):
        cut = o["cut"]
        print(f"\n[{i}] {o['outputName']}")
        print(f"    cut {cut['titleFile']} [{cut['nominalStart']:.3f} -> {cut['cutEnd']:.3f}] s, keyframe start {cut['cutStart']:.3f} (backoff {cut['keyframeBackoffSec']} s)")
        print(f"    expected {cut['expectedSeconds']} s, {cut['expectedBytes']:,} B (range video {cut['rangeVideoBytes']:,} B + audio {cut['audioBps']:,.0f} B/s)")
        for t, s in zip(cut["chapterTimes"], o["sources"]):
            print(f"    @{t:10.3f} s  {s['chapterName']}  [{s['titleFile']} ch {s['chapter']}]")
    for r in plan["coverage"]:
        print(f"coverage: {r['titleFile']} ch {r['chapter']} {r['kind']} {r['seconds']} s -> {r['disposition']}" + (f" ({r['output']})" if r["output"] else ""))
    for k, v in plan["violations"].items():
        print(f"VIOLATION: {k}: {v}")


# ---------- merge (strategy A) ----------

def global_title(path):
    code, text = run_out(["mkvextract", "tags", path])
    if code != 0 or not text.strip():
        return None
    for tag in ET.fromstring(text).findall("Tag"):
        targets = tag.find("Targets")
        if targets is not None and any(c.tag.endswith("UID") for c in targets):
            continue
        for s in tag.findall("Simple"):
            if s.findtext("Name") == "TITLE":
                return s.findtext("String")
    return None


def write_title(path, title, work):
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n<Tags>\n  <Tag>\n    <Targets>\n      <TargetTypeValue>50</TargetTypeValue>\n    </Targets>\n'
           f'    <Simple>\n      <Name>TITLE</Name>\n      <String>{escape(title)}</String>\n    </Simple>\n  </Tag>\n</Tags>\n')
    tmp = work / "tags-tmp.xml"
    tmp.write_text(xml, encoding="utf-8")
    try:
        return run(["mkvpropedit", path, "--edit", "info", "--set", f"title={title}", "--tags", f"all:{tmp}"], check=True)
    finally:
        tmp.unlink(missing_ok=True)


def merge_output(o, folder, path, work):
    srcs = [folder / s["file"] for s in o["sources"]]
    args = ["mkvmerge", "-o", path, "--title", o["mkvTitle"], "--generate-chapters", "when-appending"]
    for i, (p, s) in enumerate(zip(srcs, o["sources"])):
        if i:
            args.append("+")
        if s["chapterEntries"] or len(srcs) == 1:
            args.append("--no-chapters")
        args.append(p)
    code, merge_text = run(args, check=True)
    names = [s["chapterName"] for s in o["sources"]]
    if len(srcs) == 1:
        xml = ('<?xml version="1.0" encoding="UTF-8"?>\n<Chapters>\n  <EditionEntry>\n    <ChapterAtom>\n      <ChapterTimeStart>00:00:00.000000000</ChapterTimeStart>\n'
               f'      <ChapterDisplay>\n        <ChapterString>{escape(names[0])}</ChapterString>\n      </ChapterDisplay>\n    </ChapterAtom>\n  </EditionEntry>\n</Chapters>\n')
    else:
        _, xml = run_out(["mkvextract", "chapters", path])
        found = list(re.finditer(r"<ChapterString>.*?</ChapterString>", xml, re.S))
        if len(found) != len(names):
            raise RuntimeError(f"extracted {len(found)} chapters != {len(names)} planned")
        parts, pos = [], 0
        for m, n in zip(found, names):
            parts += [xml[pos:m.start()], f"<ChapterString>{escape(n)}</ChapterString>"]
            pos = m.end()
        xml = "".join(parts) + xml[pos:]
    tmp = work / "chapters-tmp.xml"
    tmp.write_text(xml, encoding="utf-8")
    try:
        chap_code, _ = run(["mkvpropedit", path, "--chapters", tmp], check=True)
    finally:
        tmp.unlink(missing_ok=True)
    title_code, _ = write_title(path, o["mkvTitle"], work)
    return {"mkvmergeExit": code, "mergeOutput": merge_text, "chaptersPropeditExit": chap_code, "titlePropeditExit": title_code}


# ---------- verification (six checks + title invariant) ----------

def streams(path):
    code, text = run_out(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name", "-of", "json", path])
    if code != 0:
        raise RuntimeError(f"ffprobe exit {code} on {path}")
    return [(s["codec_type"], s["codec_name"]) for s in json.loads(text)["streams"] if s["codec_type"] in ("video", "audio")]


def video_seconds(path):
    cached = cache_load("videosec", path)
    if cached:
        return cached["seconds"]
    for attempt in range(3):
        code, text = run_out(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=pts_time,duration_time", "-of", "csv=p=0", path])
        if code == 0:
            break
        time.sleep(5 * (attempt + 1))
    best = None
    for line in text.splitlines():
        parts = line.strip().split(",")
        if not parts[0] or parts[0] == "N/A":
            continue
        end = float(parts[0]) + (float(parts[1]) if len(parts) > 1 and parts[1] not in ("", "N/A") else 0.0)
        best = end if best is None or end > best else best
    if best is None:
        raise RuntimeError(f"no video packets measured on {path}")
    cache_store("videosec", path, {"seconds": best})
    return best


def verify_output(o, folder, path, merge_exit):
    srcs = [folder / s["file"] for s in o["sources"]]
    in_sec = sum(video_seconds(p) for p in srcs)
    in_bytes = sum(p.stat().st_size for p in srcs)
    in_codecs = streams(srcs[0])
    _, cj = run_out(["ffprobe", "-v", "error", "-show_chapters", "-of", "json", path])
    got = [c.get("tags", {}).get("title", "") for c in json.loads(cj).get("chapters", [])]
    want = [s["chapterName"] for s in o["sources"]]
    out_sec = video_seconds(path)
    tol = max(2.0, 0.01 * in_sec)
    out_bytes = path.stat().st_size
    size_pct = (out_bytes - in_bytes) / in_bytes * 100
    dec_code, dec_text = run(["ffmpeg", "-v", "error", "-xerror", "-i", path, "-map", "0:v", "-map", "0:a", "-f", "null", "-"])
    _, jt = run_out(["mkvmerge", "-J", path])
    segment = json.loads(jt)["container"]["properties"].get("title")
    gtitle = global_title(path)
    checks = {
        "append": {"exit": merge_exit, "pass": merge_exit is not None and merge_exit < 2},
        "chapters": {"expected": want, "actual": got, "pass": got == want},
        "duration": {"metric": "video-stream-packets", "inputSec": round(in_sec, 3), "outputSec": round(out_sec, 3), "deltaSec": round(out_sec - in_sec, 3), "toleranceSec": round(tol, 3), "pass": abs(out_sec - in_sec) <= tol},
        "codecs": {"input": in_codecs, "output": streams(path), "pass": streams(path) == in_codecs},
        "size": {"inputBytes": in_bytes, "outputBytes": out_bytes, "deltaPct": round(size_pct, 4), "bandPct": 2.0, "pass": abs(size_pct) <= 2.0},
        "decode": {"exit": dec_code, "messages": dec_text.splitlines()[:40], "pass": dec_code == 0},
        "title": {"expected": o["mkvTitle"], "segment": segment, "global": gtitle, "stem": path.stem, "pass": segment == gtitle == path.stem == o["mkvTitle"]},
    }
    return checks, all(c["pass"] for c in checks.values())


def load_approved(args, folder):
    approved = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    if approved.get("strategy") == "b":
        src = Path(approved["approvedManifest"])
        if not src.exists() or hashlib.sha256(src.read_bytes()).hexdigest() != approved["approvedManifestSha256"]:
            raise SystemExit("bound strategy-A manifest missing or changed; re-plan and re-approve")
        try:
            fresh = plan_b(folder, src, approved.get("research"), Path(approved["dest"]))
        except FileNotFoundError as e:
            raise SystemExit(f"strategy B re-plan cannot read a recorded input: {e.filename or e}; re-plan and re-approve") from e

        def shape_of(p):
            return [(o["outputName"], [s["chapterName"] for s in o["sources"]], o["cut"]["cutStart"], o["cut"]["cutEnd"]) for o in p["outputs"]]
    else:
        fresh = make_plan(folder, Path(approved["dest"]), approved.get("research"))

        def shape_of(p):
            return [(o["outputName"], [(s["file"], s["chapterName"]) for s in o["sources"]]) for o in p["outputs"]]

    if shape_of(fresh) != shape_of(approved) or fresh["tagsJsonSha256"] != approved["tagsJsonSha256"]:
        raise SystemExit("approved manifest no longer matches the folder + tags.json; re-plan and re-approve")
    if approved["violations"] or approved["unclassified"] or not approved["census"]["ok"]:
        raise SystemExit("approved manifest carries violations/unclassified/census failure")
    return approved


def cmd_merge(args, verify_only):
    folder, out_dir = Path(args.folder), Path(args.out_dir)
    plan = load_approved(args, folder)
    strategy_b = plan.get("strategy") == "b"
    if getattr(args, "strategy", None) and args.strategy != ("b" if strategy_b else "a"):
        raise SystemExit("--strategy does not match the approved manifest")
    out_dir.mkdir(parents=True, exist_ok=True)
    for o in plan["outputs"]:
        bad = name_violations(o, [out_dir])
        if bad:
            raise SystemExit(f"{o['outputName']}: {bad} under {out_dir}")
    need = 2 * sum(o["sourceBytes"] for o in plan["outputs"] if not (out_dir / o["outputName"]).exists())
    free = shutil.disk_usage(out_dir).free
    if not verify_only and free < need:
        raise SystemExit(f"space guard: free {free:,} B < 2x expected {need:,} B")
    title_snap = {}
    if strategy_b:
        for tf in {o["cut"]["titleFile"] for o in plan["outputs"]}:
            st = (folder / tf).stat()
            title_snap[tf] = {"bytes": st.st_size, "mtime": st.st_mtime_ns}
    runlog = out_dir / "runlog.json"
    ok_all = True
    for o in plan["outputs"]:
        path = out_dir / o["outputName"]
        row = {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "rowType": "output", "folder": str(folder), "output": o["outputName"],
               "strategy": "b" if strategy_b else "a",
               "mode": "verify" if verify_only else "merge", "approvedBy": getattr(args, "approved_by", None), "resumed": path.exists(),
               "sourcesCount": len(o["sources"]), "missingChaptersCount": len(o.get("missingChapters", [])), "pass": False, "error": None}
        print(f"--- {o['outputName']}")
        try:
            build_exit = None
            exit_key = "ffmpegExit" if strategy_b else "mkvmergeExit"
            if path.exists():
                print("    existing output: verify only, never overwritten")
                prior = [json.loads(l) for l in runlog.read_text(encoding="utf-8").splitlines() if l.strip()] if runlog.exists() else []
                build_exit = next((r.get(exit_key) for r in reversed(prior) if r.get("output") == o["outputName"] and r.get(exit_key) is not None), None)
            elif verify_only:
                raise RuntimeError("output missing")
            elif strategy_b:
                row.update(cut_output(o, folder, path, out_dir))
                build_exit = row["ffmpegExit"]
            else:
                row.update(merge_output(o, folder, path, out_dir))
                build_exit = row["mkvmergeExit"]
            if strategy_b:
                row["checks"], row["pass"], row["comparison"] = verify_output_b(o, folder, path, build_exit)
            else:
                row["checks"], row["pass"] = verify_output(o, folder, path, build_exit)
            for k, c in row["checks"].items():
                print(f"    {k}: {'PASS' if c['pass'] else 'FAIL'}  {json.dumps({x: y for x, y in c.items() if x not in ('pass', 'messages', 'expected', 'actual')}, ensure_ascii=False)[:300]}")
            if strategy_b:
                cmp = row["comparison"]
                print(f"    vs approved: name={cmp['nameMatch']} chapters={cmp['chaptersMatch']} durDelta={cmp['durationDeltaSec']}s segmentBytes={cmp['segmentBytesMatch']} globalBytes={cmp['globalBytesMatch']}")
                if not (cmp["nameMatch"] and cmp["chaptersMatch"] and cmp["segmentBytesMatch"] and cmp["globalBytesMatch"]):
                    row["pass"] = False
        except Exception as e:
            row["error"] = str(e)
            print(f"    FAILED: {e}")
        with runlog.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        if not row["pass"]:
            ok_all = False
            print("folder stopped at first failure; nothing repaired, every source kept")
            break
    title_ok = True
    if strategy_b:
        for tf, snap in title_snap.items():
            st = (folder / tf).stat()
            if st.st_size != snap["bytes"] or st.st_mtime_ns != snap["mtime"]:
                title_ok = False
        summary = {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "rowType": "folder-summary", "folder": str(folder),
                   "strategy": "b", "titleRipsUnchanged": title_ok, "coverage": plan["census"], "pass": ok_all and title_ok}
        with runlog.open("a", encoding="utf-8") as f:
            f.write(json.dumps(summary, ensure_ascii=False) + "\n")
        print(f"title rips unchanged: {title_ok}; coverage: {plan['census']}")
        ok_all = ok_all and title_ok
    print("FOLDER PASS" if ok_all else "FOLDER FAIL")
    return 0 if ok_all else 1


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    p.add_argument("folder")
    p.add_argument("--out")
    p.add_argument("--dest")
    p.add_argument("--research")
    p.add_argument("--strategy", choices=["a", "b"])
    p.add_argument("--manifest", help="approved strategy-A manifest (required for strategy B)")
    p.add_argument("--cache", help="scratch dir for stat-keyed probe caches (packet index, video duration)")
    for name in ("merge", "verify"):
        m = sub.add_parser(name)
        m.add_argument("folder")
        m.add_argument("--manifest", required=True)
        m.add_argument("--out-dir", required=True)
        m.add_argument("--strategy", choices=["a", "b"])
        m.add_argument("--cache")
        if name == "merge":
            m.add_argument("--approved-by", required=True)
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    global CACHE_DIR
    if getattr(args, "cache", None):
        CACHE_DIR = Path(args.cache)
    if args.cmd == "plan":
        folder = Path(args.folder)
        strategy = args.strategy
        if strategy is None:
            shape, _ = detect_shape(folder)
            strategy = "a" if shape == "movement-rips" else "b"
        dest = Path(args.dest) if args.dest else folder
        if strategy == "b":
            if not args.manifest:
                raise SystemExit("strategy B re-curates an approved manifest: pass --manifest <approved strategy-A manifest>")
            plan = plan_b(folder, args.manifest, args.research, dest)
            print_plan_b(plan)
        else:
            plan = make_plan(folder, dest, args.research)
            print_plan(plan)
        if args.out:
            Path(args.out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.out).write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"\nmanifest written: {args.out}")
        return 0 if plan["census"]["ok"] and not plan["violations"] and not plan["unclassified"] else 1
    return cmd_merge(args, args.cmd == "verify")


if __name__ == "__main__":
    sys.exit(main())

