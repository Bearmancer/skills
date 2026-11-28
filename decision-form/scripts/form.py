import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from argparse import ArgumentParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PAGE = Path(__file__).parents[1] / "assets" / "form.html"
BUNDLED = re.compile(r"[,;/+&|]|\b(?:and|or|nor|plus|all|both|every|everything|either|each|rest|etc)\b", re.IGNORECASE)
SHAPE = {"projects": ("name", "url"), "issues": ("id", "title", "url", "status"), "labels": ("name",), "documents": ("title", "url")}


def run(*args, body=None):
    return subprocess.run(args, input=body, capture_output=True, encoding="utf-8", check=True).stdout


def blank(item, key):
    return not isinstance(item.get(key), str) or not item[key].strip()


def problems(form):
    found = ["form: missing title"] if blank(form, "title") else []
    if not form.get("questions"):
        found.append("form: no questions")
    ids = {"else"}
    for number, question in enumerate(form.get("questions", []), 1):
        where = question.get("id") or f"question {number}"
        found += [f"{where}: missing {key}" for key in ("id", "title", "text", "explain") if blank(question, key)]
        if question.get("id") in ids:
            found.append(f"{where}: id taken")
        ids.add(question.get("id"))
        if not question.get("options"):
            found.append(f"{where}: no options")
        labels = set()
        for option in question.get("options", []):
            found += [f"{where}: box missing {key}" for key in ("label", "explain") if blank(option, key)]
            label = str(option.get("label", ""))
            if hit := BUNDLED.search(label):
                found.append(f'{where}: "{label}" bundles items ("{hit[0]}"). One box per item.')
            if label in labels:
                found.append(f'{where}: duplicate box "{label}"')
            labels.add(label)
    return found


def gaps(linear):
    found = [f"linear.json: missing {key}" for key in ("team", "read") if blank(linear, key)]
    for section, keys in SHAPE.items():
        if not isinstance(linear.get(section), list):
            found.append(f"linear.json: {section} is not a list")
            continue
        found += [f"linear.json: {section}[{n}] missing {key}" for n, row in enumerate(linear[section]) for key in keys if blank(row, key)]
    if found:
        return found
    names = {project["name"] for project in linear["projects"]}
    if not names:
        found.append("linear.json: no projects")
    return found + [f"linear.json: {i['id']} project {i.get('project')!r} not in projects" for i in linear["issues"] if i.get("project") not in names | {None}]


def checked(path, check):
    if not path.exists():
        raise SystemExit(f"{path.name} missing in {path.parent}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if found := check(data):
        raise SystemExit("\n".join(found))
    return data


def load(folder):
    return checked(folder / "questions.json", problems)


def taxonomy(folder):
    return checked(folder / "linear.json", gaps)


def where(folder):
    return os.path.normcase(str(folder.resolve()))


def gist_id(folder):
    text = (folder / "gist-id.txt").read_text(encoding="utf-8").strip()
    if text.startswith("{"):
        record = json.loads(text)
        if record["folder"] != where(folder):
            raise SystemExit(f"gist-id.txt belongs to {record['folder']}, not this folder. Delete it and run prepare.")
        return record["id"]
    if where(folder).startswith(os.path.normcase(tempfile.gettempdir())):
        raise SystemExit("gist-id.txt in a temp folder is not bound to it. Delete it and run prepare.")
    return text


def saved(gist):
    data = json.loads(run("gh", "api", f"gists/{gist}"))
    return json.loads(data["files"]["answers.json"]["content"]), data["updated_at"]


def sigs(form):
    return {q["id"]: hashlib.sha256(json.dumps([q["title"], q["text"], q["explain"], [[o["label"], o["explain"]] for o in q["options"]]]).encode()).hexdigest()[:12] for q in form["questions"]}


def current(form, answers):
    marks = sigs(form)
    return {key: answer for key, answer in answers.items() if (key in marks or key == "else") and answer.get("sig", marks.get(key)) == marks.get(key)}


def clean(form, sent):
    allowed = {q["id"]: [o["label"] for o in q["options"]] for q in form["questions"]} | {"else": []}
    marks = sigs(form)
    kept = {}
    for key, answer in sent.items():
        ticked, note = answer["ticked"], answer["note"]
        if not set(ticked) <= set(allowed[key]):
            raise ValueError(f"unknown box in {key}")
        if note.strip() or ticked:
            kept[key] = {"ticked": [label for label in allowed[key] if label in ticked], "note": note, "sig": marks.get(key)}
    return kept


def prepare(folder):
    form = load(folder)
    taxonomy(folder)
    record = folder / "gist-id.txt"
    if not record.exists():
        body = {"description": form["title"], "public": False, "files": {"answers.json": {"content": "{}"}}}
        record.write_text(json.dumps({"id": json.loads(run("gh", "api", "gists", "--input", "-", body=json.dumps(body)))["id"], "folder": where(folder)}), encoding="utf-8")
    print(f"ready: {len(form['questions'])} questions")
    print(f"gist: https://gist.github.com/{gist_id(folder)}")


def read(folder):
    form = load(folder)
    answers = current(form, saved(gist_id(folder))[0])
    (folder / "answers.json").write_text(json.dumps(answers, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for question in [*form["questions"], {"id": "else", "title": "Anything else"}]:
        if answer := answers.get(question["id"]):
            print(f"[{question['id']}] {question['title']}")
            for label in answer["ticked"]:
                print(f"  ticked: {label}")
            if answer["note"].strip():
                print(f"  note: {answer['note']}")
    print("open:", " ".join(q["id"] for q in form["questions"] if q["id"] not in answers) or "none")


def serve(folder, port):
    form, linear, gist = load(folder), taxonomy(folder), gist_id(folder)
    host = json.loads(run("tailscale", "status", "--json"))["Self"]["DNSName"].rstrip(".")
    origins = {f"127.0.0.1:{port}": f"http://127.0.0.1:{port}", f"{host}:{port}": f"https://{host}:{port}"}

    class Handler(BaseHTTPRequestHandler):
        def reply(self, code, body, kind):
            self.send_response(code)
            self.send_header("Content-Type", f"{kind}; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def answer(self, work):
            try:
                self.reply(200, json.dumps(work()).encode(), "application/json")
            except subprocess.CalledProcessError as error:
                self.reply(502, error.stderr.strip().encode(), "text/plain")

        def do_GET(self):
            if self.headers.get("Host") not in origins:
                self.send_error(404)
            elif self.path == "/":
                self.reply(200, PAGE.read_bytes(), "text/html")
            elif self.path == "/form.json":
                def page():
                    answers, version = saved(gist)
                    return {"key": gist, "form": form, "linear": linear, "saved": current(form, answers), "version": version, "sigs": sigs(form)}

                self.answer(page)
            else:
                self.send_error(404)

        def do_POST(self):
            origin = origins.get(self.headers.get("Host"))
            if not origin or self.headers.get("Origin") != origin or self.path != "/submit":
                return self.send_error(403)
            try:
                kept = clean(form, json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            except (AttributeError, KeyError, TypeError, ValueError) as error:
                return self.reply(400, f"bad answers: {error}".encode(), "text/plain")

            def push():
                content = json.dumps(kept, indent=2, ensure_ascii=False)
                body = json.dumps({"files": {"answers.json": {"content": content}}})
                version = json.loads(run("gh", "api", f"gists/{gist}", "-X", "PATCH", "--input", "-", body=body))["updated_at"]
                return {"msg": f"Saved to gist: {len(kept.keys() - {'else'})} answered", "version": version}

            self.answer(push)

    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    parser = ArgumentParser()
    parser.add_argument("command", choices=("prepare", "serve", "read"))
    parser.add_argument("folder", type=Path)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if args.command == "serve":
        serve(args.folder, args.port)
    else:
        {"prepare": prepare, "read": read}[args.command](args.folder)
