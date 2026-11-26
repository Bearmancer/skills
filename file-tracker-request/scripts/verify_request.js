// Post-submit readback diff. Run on requests.php?action=view&id=<new id> with the
// same payload stashed in <pre id="__payload">. Reads the rendered tag and artist
// LINKS (never page text: the description repeats the names and masks a broken
// row) and writes {ok, missingTags, extraTags, missingArtists, ...} to
// <pre id="__verify_result">. Stop the batch on the first ok:false.
(function () {
  var out = document.getElementById('__verify_result') || document.createElement('pre');
  out.id = '__verify_result';
  out.style.display = 'none';
  document.body.appendChild(out);
  try {
    var payload = JSON.parse(document.getElementById('__payload').textContent);
    var c = document.getElementById('content');
    var text = function (sel) {
      return Array.from(c.querySelectorAll(sel)).map(function (a) { return a.textContent.trim(); });
    };
    var tags = text("a[href*='taglist='], a[href*='tags=']");
    var artists = text("a[href*='artist.php']");
    var want = payload.tag_list || String(payload.tags).split(',').map(function (t) { return t.trim(); });
    // RED may append a canonical alias: "Tokyo Symphony Orchestra (東京交響楽団)".
    var hasArtist = function (n) {
      return artists.some(function (a) { return a === n || a.indexOf(n + ' (') === 0; });
    };
    var res = {
      url: location.href,
      missingTags: want.filter(function (t) { return tags.indexOf(t) === -1; }),
      extraTags: tags.filter(function (t) { return want.indexOf(t) === -1; }),
      missingArtists: payload.artists.map(function (a) { return a.name; }).filter(function (n) { return !hasArtist(n); }),
      badArtists: artists.filter(function (a) { return /^[\d\s.]*$/.test(a); }),
      catalogue: c.innerText.indexOf(payload.cataloguenumber) !== -1
    };
    res.ok = /action=view&id=\d+/.test(location.href) && !res.missingTags.length && !res.extraTags.length &&
      !res.missingArtists.length && !res.badArtists.length && res.catalogue;
    out.textContent = JSON.stringify(res);
  } catch (e) {
    out.textContent = JSON.stringify({ ok: false, error: String((e && e.stack) || e) });
  }
})();
