/* shell.js — wires the A-bar: topic picker, chapter picker, font menu, size menu.
   Persists font + size in localStorage; every storage access is try/catch
   wrapped since file:// and locked-down browsers can throw. */
(function() {
	var FONTS = [
		["Literata", "Literata:opsz,wght@7..72,400;7..72,600"],
		["Source Serif 4", "Source+Serif+4:opsz,wght@8..60,400;8..60,600"],
		["Newsreader", "Newsreader:opsz,wght@6..72,400;6..72,600"],
		["Crimson Pro", "Crimson+Pro:wght@400;600"],
		["EB Garamond", "EB+Garamond:wght@400;600"],
		["Merriweather", "Merriweather:wght@400;700"],
		["Lora", "Lora:wght@400;600"],
		["Libre Baskerville", "Libre+Baskerville:wght@400;700"],
		["Atkinson Hyperlegible", "Atkinson+Hyperlegible:wght@400;700"],
		["Inter", "Inter:wght@400;600"],
		["IBM Plex Sans", "IBM+Plex+Sans:wght@400;600"],
		["Charter", null],
	];
	var root = document.documentElement;
	var store = {
		get: function(k) {
			try {
				return localStorage.getItem(k);
			} catch (e) {
				return null;
			}
		},
		set: function(k, v) {
			try {
				localStorage.setItem(k, v);
			} catch (e) {}
		},
	};

	var THEMES = ["auto", "light", "dark"];

	function setTheme(t) {
		if (THEMES.indexOf(t) < 0) t = "auto";
		if (t === "auto") root.removeAttribute("data-theme");
		else root.setAttribute("data-theme", t);
		store.set("theme", t);
		document.querySelectorAll("[data-theme-toggle]").forEach(function(b) {
			b.textContent = "Theme: " + t;
			b.setAttribute("aria-label", "Colour theme: " + t + ". Activate to change.");
			b.setAttribute("aria-pressed", t === "auto" ? "false" : "true");
		});
	}

	document.querySelectorAll("[data-theme-toggle]").forEach(function(b) {
		b.onclick = function() {
			var cur = store.get("theme") || "auto";
			setTheme(THEMES[(THEMES.indexOf(cur) + 1) % THEMES.length]);
		};
	});
	setTheme(store.get("theme") || "auto");

	function loadFont(name) {
		var f = null;
		for (var i = 0; i < FONTS.length; i++) {
			if (FONTS[i][0] === name) {
				f = FONTS[i];
				break;
			}
		}
		if (f && f[1] && !document.querySelector("link[data-font=\"" + name + "\"]")) {
			var l = document.createElement("link");
			l.rel = "stylesheet";
			l.dataset.font = name;
			l.href = "https://fonts.googleapis.com/css2?family=" + f[1] + "&display=swap";
			document.head.appendChild(l);
		}
		root.style.setProperty("--font-body", "\"" + name + "\", Charter, Georgia, serif");
		store.set("font", name);
	}

	function setSize(s) {
		root.dataset.size = s;
		store.set("size", s);
	}

	document.querySelectorAll("[data-font-select]").forEach(function(s) {
		s.onchange = function(e) {
			loadFont(e.target.value);
		};
	});
	document.querySelectorAll("[data-size-select]").forEach(function(s) {
		s.onchange = function(e) {
			setSize(e.target.value);
		};
	});

	var savedFont = store.get("font");
	if (savedFont) {
		loadFont(savedFont);
		document.querySelectorAll("[data-font-select]").forEach(function(s) {
			s.value = savedFont;
		});
	}
	var savedSize = store.get("size");
	if (savedSize) {
		setSize(savedSize);
		document.querySelectorAll("[data-size-select]").forEach(function(s) {
			s.value = savedSize;
		});
	}

	function fill(sel, entries, base) {
		while (sel.firstChild) sel.removeChild(sel.firstChild);
		var frag = document.createDocumentFragment();
		if (sel.dataset.placeholder) {
			var p = document.createElement("option");
			p.value = "";
			p.textContent = sel.dataset.placeholder;
			frag.appendChild(p);
		}
		entries.forEach(function(c) {
			var o = document.createElement("option");
			o.value = base + c.href;
			o.textContent = c.label;
			if (c.id === sel.dataset.current) o.selected = true;
			frag.appendChild(o);
		});
		sel.appendChild(frag);
		// A page missing from its own list (a verify page) still shows itself, so the select always names where you are.
		if (
			sel.dataset.current && !sel.dataset.placeholder && !entries.some(function(c) {
				return c.id === sel.dataset.current;
			})
		) {
			var here = document.createElement("option");
			here.value = "";
			here.textContent = document.title;
			here.selected = true;
			sel.insertBefore(here, sel.firstChild);
		}
		sel.onchange = function(e) {
			if (e.target.value) location.href = e.target.value;
		};
	}

	// Every feed defines window.COURSE_INDEX: read one, then restore the page's own list.
	// A feed that fails to load reads as empty.
	function loadFeed(src, done) {
		var keep = window.COURSE_INDEX;
		var s = document.createElement("script");
		function finish(list) {
			window.COURSE_INDEX = keep;
			s.remove();
			done(list);
		}
		s.onload = function() {
			finish(window.COURSE_INDEX || []);
		};
		s.onerror = function() {
			finish([]);
		};
		s.src = src;
		document.head.appendChild(s);
	}

	var chapters = window.COURSE_INDEX || [];
	document.querySelectorAll("[data-index]").forEach(function(sel) {
		if (sel.hasAttribute("data-follows-topic")) {
			fill(sel, [], "");
			if (sel.parentNode) sel.parentNode.hidden = true;
			return;
		}
		fill(sel, chapters, sel.dataset.base || "");
	});
	document.querySelectorAll("[data-topic]").forEach(function(sel) {
		var base = sel.dataset.base || "";
		var follower = sel.closest(".A-bar").querySelector("[data-follows-topic]");
		function ready(topics) {
			fill(sel, topics, base);
			if (!follower) return;
			var holder = follower.parentNode;
			sel.onchange = function(e) {
				var entry = topics.filter(function(t) {
					return base + t.href === e.target.value;
				})[0];
				var list = entry && entry.chapters;
				follower.dataset.current = "";
				if (!list || list.length < 2) {
					fill(follower, [], "");
					holder.hidden = true;
					if (entry) location.href = e.target.value;
					return;
				}
				fill(follower, list, base);
				holder.hidden = false;
			};
		}
		if (sel.dataset.feed) loadFeed(sel.dataset.feed, ready);
		else ready(chapters);
	});
})();
