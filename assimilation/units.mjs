// Splits a source file into Units: contiguous slices whose concatenation is the exact original bytes.
// Granularity comes from the markdown structure; correctness (nothing lost) comes from contiguity,
// which holds by construction and is re-checked independently by `enumerate.mjs verify`.

const HEAD = /^ {0,3}(#{1,6})[ \t]+/;
const FENCE = /^(\s*)(`{3,}|~{3,})/;
const TABLE = /^\s*\|/;
const TABLE_SEP = /^[\s|:-]+$/;
const HR = /^ {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*\r?\n?$/;
const QUOTE = /^ {0,3}>/;
const LIST = /^([ \t]*)([-*+]|\d+[.)])(?:[ \t]+|\r?\n?$)/;
const FM_DELIM = /^---[ \t]*\r?\n?$/;

const blank = (l) => l.trim() === "";
const indentOf = (l) => l.match(/^[ \t]*/)[0].replace(/\t/g, "    ").length;
const startsBlock = (l) =>
	HEAD.test(l) || FENCE.test(l) || TABLE.test(l) || HR.test(l) || QUOTE.test(l) || LIST.test(l);

export function splitMarkdown(text) {
	const lines = text.match(/[^\n]*\n|[^\n]+$/g) ?? [];
	const n = lines.length;
	const blocks = [];
	const stack = [];
	const section = () => stack.map((h) => h.text).join(" > ");
	const push = (kind, s, e, depth = 0, sec = section()) => blocks.push({ kind, depth, s, e, section: sec });

	let i = 0;
	if (n > 0 && FM_DELIM.test(lines[0])) {
		let close = -1;
		for (let j = 1; j < n; j++) {
			if (FM_DELIM.test(lines[j])) {
				close = j;
				break;
			}
		}
		if (close > 0) {
			let start = -1;
			for (let j = 1; j < close; j++) {
				if (start < 0 || /^[^\s#][^:\n]*:/.test(lines[j])) {
					if (start >= 0) push("fm-field", start, j, 0, "frontmatter");
					start = j;
				}
			}
			if (start >= 0) push("fm-field", start, close, 0, "frontmatter");
			i = close + 1;
		}
	}

	while (i < n) {
		const l = lines[i];
		if (blank(l)) {
			i++;
			continue;
		}
		let m;
		if ((m = HEAD.exec(l))) {
			const level = m[1].length;
			const t = l.slice(m[0].length).replace(/[ \t]+#+[ \t]*\r?\n?$/, "").trim();
			while (stack.length && stack.at(-1).level >= level) stack.pop();
			stack.push({ level, text: t });
			push("heading", i, i + 1);
			i++;
			continue;
		}
		if ((m = FENCE.exec(l))) {
			const ch = m[2][0];
			const closer = new RegExp(`^\\s*\\${ch}{${m[2].length},}[ \\t]*\\r?\\n?$`);
			let j = i + 1;
			while (j < n && !closer.test(lines[j])) j++;
			const e = Math.min(j + 1, n);
			push("code", i, e, Math.floor(indentOf(l) / 2));
			i = e;
			continue;
		}
		if (HR.test(l)) {
			push("rule", i, i + 1);
			i++;
			continue;
		}
		if (TABLE.test(l)) {
			push(TABLE_SEP.test(l) ? "table-sep" : "table-row", i, i + 1);
			i++;
			continue;
		}
		if (QUOTE.test(l)) {
			let j = i + 1;
			while (j < n && !blank(lines[j]) && QUOTE.test(lines[j])) j++;
			push("quote", i, j);
			i = j;
			continue;
		}
		if ((m = LIST.exec(l))) {
			const indent = indentOf(l);
			let j = i + 1;
			while (j < n) {
				const t = lines[j];
				if (blank(t)) {
					let k = j;
					while (k < n && blank(lines[k])) k++;
					if (k < n && indentOf(lines[k]) > indent && !startsBlock(lines[k])) {
						j = k + 1;
						continue;
					}
					break;
				}
				if (startsBlock(t)) break;
				j++;
			}
			push("list-item", i, j, Math.floor(indent / 2));
			i = j;
			continue;
		}
		let j = i + 1;
		while (j < n && !blank(lines[j]) && !startsBlock(lines[j])) j++;
		push("para", i, j);
		i = j;
	}

	// Rules and table separators carry no content of their own: fold them into the unit before them.
	const out = [];
	for (const b of blocks) {
		const prev = out.at(-1);
		if (prev && (b.kind === "rule" || b.kind === "table-sep")) {
			prev.e = b.e;
			continue;
		}
		out.push({ ...b });
	}
	if (out.length === 0) {
		return n === 0 ? [] : [{ kind: "blank", depth: 0, s: 0, e: n, section: "" }].map((b) => finish(b, lines));
	}
	// Blank lines belong to the unit before them (or the first unit); this is what makes the slices contiguous.
	out[0].s = 0;
	for (let k = 0; k < out.length - 1; k++) out[k].e = out[k + 1].s;
	out.at(-1).e = n;
	const off = [0];
	for (const l of lines) off.push(off.at(-1) + Buffer.byteLength(l));
	return out.map((b) => finish(b, lines, off));
}

function finish(b, lines, off) {
	if (!off) {
		off = [0];
		for (const l of lines) off.push(off.at(-1) + Buffer.byteLength(l));
	}
	return {
		kind: b.kind,
		depth: b.depth,
		section: b.section,
		lines: [b.s + 1, b.e],
		bytes: [off[b.s], off[b.e]],
		text: lines.slice(b.s, b.e).join(""),
	};
}

// Text normalised for exact-duplicate detection only (never used to decide meaning).
export const norm = (t) =>
	t
		.replace(/^\s*(?:[-*+]|\d+[.)])\s+/, "")
		.toLowerCase()
		.replace(/[`*_>|#]/g, " ")
		.replace(/\s+/g, " ")
		.trim();

export function fileUnits(rel, buf) {
	const str = buf.toString("utf8");
	if (!Buffer.from(str, "utf8").equals(buf)) {
		return [{ kind: "binary", depth: 0, section: "", lines: [0, 0], bytes: [0, buf.length], text: null }];
	}
	const isMd = /\.md$/i.test(rel);
	if (isMd) {
		const units = splitMarkdown(str);
		if (units.length) return units;
	}
	return [
		{
			kind: isMd ? "blank" : "file",
			depth: 0,
			section: "",
			lines: [1, str.split("\n").length],
			bytes: [0, buf.length],
			text: str,
		},
	];
}
