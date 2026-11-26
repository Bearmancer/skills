(async function () {
  var out = document.createElement('pre');
  out.id = '__fill_result';
  out.style.display = 'none';
  document.body.appendChild(out);
  try {
    var payload = JSON.parse(document.getElementById('__payload').textContent);
    var site = payload.site || 'red';
    var form = document.querySelector('form#request_form:not(.add_form)');
    if (!form) throw new Error('main request form not found');
    var fire = function (el, t) { el.dispatchEvent(new Event(t, { bubbles: true })); };
    var breathe = function () { return new Promise(function (r) { setTimeout(r, 0); }); };
    var errs = [];
    // Lint before touching the form: Gazelle splits tags ONLY on commas and strips
    // ';' and '-', so a wrongly joined string posts as one merged tag; a numeric or
    // empty artist name posts as an artist literally called "1".
    var tagList = String(payload.tags || '').split(',').map(function (t) { return t.trim(); });
    tagList.forEach(function (t) {
      if (!/^[a-z0-9]+(\.[a-z0-9]+)*$/.test(t)) errs.push('bad tag "' + t + '" (use build_payload.py)');
    });
    if (tagList.indexOf('classical') === -1) errs.push('tags lack classical');
    if (String(payload.tags || '').length > 200) errs.push('tags over 200 chars');
    payload.artists.forEach(function (a) {
      if (typeof a.name !== 'string' || !a.name.trim() || /^[\d\s.]+$/.test(a.name)) errs.push('bad artist name ' + JSON.stringify(a));
    });
    if (errs.length) throw new Error('payload lint: ' + errs.join('; '));
    var q = function (s) { return form.querySelector(s); };
    var qa = function (s) { return Array.from(form.querySelectorAll(s)); };

    var cat = q('#categories');
    cat.value = payload.type;
    fire(cat, 'change');

    var guard = 0;
    while (qa('input[name="artists[]"]').length < payload.artists.length && guard++ < 220) {
      if (site === 'ops') {
        if (typeof artist_add === 'function') artist_add(); else q('#artist-add').click();
      } else {
        AddArtistField();
      }
      if (guard % 10 === 0) await breathe();
    }
    var aI = qa('input[name="artists[]"]');
    var aS = qa('select[name="importance[]"]');
    if (aI.length !== payload.artists.length || aS.length !== payload.artists.length) errs.push('rows ' + aI.length + '/' + aS.length);
    var roles = {};
    for (var i = 0; i < payload.artists.length; i++) {
      aI[i].value = payload.artists[i].name;
      aS[i].value = String(payload.artists[i].role);
      fire(aS[i], 'change');
      roles[aS[i].value] = (roles[aS[i].value] || 0) + 1;
      if (i % 20 === 0) await breathe();
    }

    [['title', 'title'], ['recordlabel', 'recordlabel'], ['cataloguenumber', 'cataloguenumber'],
     ['year', 'year'], ['image', 'image'], ['oclc', 'oclc'], ['groupid', 'groupid']].forEach(function (p) {
      var el = q('input[name="' + p[0] + '"]');
      if (!el) { if (p[0] !== 'oclc' && p[0] !== 'groupid') errs.push('missing ' + p[0]); return; }
      el.value = payload[p[1]] || '';
      fire(el, 'change');
    });
    var rt = q('#releasetype');
    rt.value = payload.releasetype;
    fire(rt, 'change');

    [['all_formats', 'all_bitrates', 'all_media']].forEach(function (masters) {
      masters.forEach(function (m) {
        var el = q('input[name="' + m + '"]');
        if (el && el.checked) { el.checked = false; fire(el, 'change'); }
      });
    });
    [['formats[]', payload.formats], ['bitrates[]', payload.bitrates], ['media[]', payload.media]].forEach(function (pair) {
      qa('input[name="' + pair[0] + '"]').forEach(function (el) {
        var want = pair[1].indexOf(el.value) !== -1;
        if (el.checked !== want) { el.checked = want; fire(el, 'change'); }
      });
    });
    await breathe();

    ['needlog', 'needcue', 'needchecksum', 'needcksum'].forEach(function (id) {
      var el = q('#' + id);
      if (el) { el.checked = payload[id] === true; fire(el, 'change'); }
    });

    var desc = q('#description');
    desc.value = payload.description;
    fire(desc, 'change');
    // Tags last: the genre dropdown and OPS handlers rewrite #tags.
    var tags = q('#tags');
    tags.value = payload.tags;
    fire(tags, 'change');
    await breathe();
    if (tags.value !== payload.tags) errs.push('tags rewritten by page: ' + tags.value);

    var ab = q('#amount_box');
    ab.value = payload.bounty.amount_box;
    fire(ab, 'input');
    fire(ab, 'change');
    var unit = q('#unit');
    unit.value = payload.bounty.unit;
    fire(unit, 'input');
    fire(unit, 'change');
    if (typeof Calculate === 'function') Calculate();

    var amount = q('#amount').value;
    var checked = function (n) { return qa('input[name="' + n + '"]:checked').map(function (e) { return e.value; }); };
    var afterTax = q('#bounty_after_tax');
    var res = {
      site: site, errs: errs, artistRows: aI.length, roles: roles,
      artists: aI.map(function (e) { return e.value; }), tags: tags.value,
      title: q('input[name="title"]').value, year: q('input[name="year"]').value,
      image: q('input[name="image"]').value.slice(0, 60),
      amount: amount, expected: String(payload.bounty.bytes),
      buttonDisabled: q('#button').disabled, descLen: desc.value.length,
      needlog: q('#needlog') ? q('#needlog').checked : null,
      needcue: q('#needcue') ? q('#needcue').checked : null,
      formats: checked('formats[]'), bitrates: checked('bitrates[]'), media: checked('media[]'),
      bountyAfterTax: afterTax ? afterTax.textContent : null
    };
    res.ok = errs.length === 0 && amount === res.expected && !res.buttonDisabled &&
      res.artistRows === payload.artists.length;
    out.textContent = JSON.stringify(res);
  } catch (e) {
    out.textContent = JSON.stringify({ ok: false, error: String((e && e.stack) || e) });
  }
})();
