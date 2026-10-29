// Shoal docs: theme switching, search, copy buttons, the mobile menu, the contents highlight.
// No dependencies.
(function () {
  "use strict";

  var root = document.documentElement;
  var reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  var prefersDark = window.matchMedia("(prefers-color-scheme: dark)");

  function store(key, value) {
    try { localStorage.setItem(key, value); } catch (error) {}
  }

  // ---------- Theme ----------

  function isDark() {
    var theme = root.dataset.theme;
    return theme === "dark" || (theme === "auto" && prefersDark.matches);
  }

  document.querySelectorAll("[data-theme-toggle]").forEach(function (button) {
    button.addEventListener("click", function () {
      var next = isDark() ? "light" : "dark";
      if (!reducedMotion.matches) {
        root.classList.add("theme-switching");
        setTimeout(function () { root.classList.remove("theme-switching"); }, 350);
      }
      root.dataset.theme = next;
      store("shoal-theme", next);
      document.dispatchEvent(new CustomEvent("shoal:theme"));
    });
  });
  prefersDark.addEventListener("change", function () {
    document.dispatchEvent(new CustomEvent("shoal:theme"));
  });

  // ---------- Copy buttons ----------

  function copy(text, button, label) {
    if (!navigator.clipboard) return;
    navigator.clipboard.writeText(text).then(function () {
      button.textContent = "Copied";
      button.setAttribute("data-copied", "");
      setTimeout(function () {
        button.textContent = label;
        button.removeAttribute("data-copied");
      }, 1600);
    });
  }

  document.querySelectorAll("[data-copy]").forEach(function (button) {
    var source = button.parentElement.querySelector("[data-copy-source]");
    button.addEventListener("click", function () { copy(source.textContent.trim(), button, "Copy"); });
  });

  document.querySelectorAll(".prose .highlight").forEach(function (block) {
    if (block.closest(".doc-signature")) return;
    var code = block.querySelector("pre");
    if (!code) return;
    var button = document.createElement("button");
    button.type = "button";
    button.className = "copy-code";
    button.textContent = "Copy";
    button.setAttribute("aria-label", "Copy this code");
    button.addEventListener("click", function () { copy(code.innerText.replace(/\n$/, ""), button, "Copy"); });
    block.appendChild(button);
  });

  // ---------- Tables ----------

  document.querySelectorAll(".prose table").forEach(function (table) {
    if (table.parentElement.classList.contains("table-scroll")) return;
    var wrapper = document.createElement("div");
    wrapper.className = "table-scroll";
    table.parentNode.insertBefore(wrapper, table);
    wrapper.appendChild(table);
  });

  // ---------- Coverage marks and routes ----------
  // The coverage page stays plain Markdown (yes, no, `GET /path`) for llms.txt and its check; here a
  // status becomes a mark and a route's method a pill.

  var STATUSES = { yes: "Implemented", no: "Not implemented", deprecated: "Deprecated", disabled: "Disabled" };
  document.querySelectorAll(".prose table").forEach(function (table) {
    var first = table.querySelector("th");
    if (!first || first.textContent.trim() !== "") return;
    table.classList.add("status-table");
    table.querySelectorAll("tbody tr").forEach(function (row) {
      var cell = row.cells[0];
      var status = cell && cell.textContent.trim();
      if (!STATUSES[status]) return;
      cell.textContent = "";
      var mark = document.createElement("span");
      mark.className = "status status-" + status;
      mark.title = STATUSES[status];
      mark.textContent = status === "yes" || status === "no" ? STATUSES[status] : status;
      cell.appendChild(mark);
    });
  });
  document.querySelectorAll(".prose td > code").forEach(function (code) {
    var route = /^(GET|POST|PUT|PATCH|DELETE) (\/\S*)$/.exec(code.textContent);
    if (!route) return;
    var method = document.createElement("span");
    method.className = "method method-" + route[1].toLowerCase();
    method.textContent = route[1];
    code.textContent = route[2];
    code.classList.add("route");
    code.parentNode.insertBefore(method, code);
  });
  // A route column moves under its endpoint's name: three columns read better than four.
  document.querySelectorAll(".status-table").forEach(function (table) {
    var heads = table.querySelectorAll("thead th");
    if (heads.length !== 4 || heads[3].textContent.trim() !== "Route") return;
    heads[3].remove();
    table.classList.add("has-routes");
    table.querySelectorAll("tbody tr").forEach(function (row) {
      var route = row.cells[3];
      var line = document.createElement("span");
      line.className = "route-line";
      while (route.firstChild) line.appendChild(route.firstChild);
      row.cells[1].appendChild(line);
      route.remove();
    });
  });

  // ---------- Start-up race ----------
  // The bars grow once, when they first come into view.

  var races = document.querySelectorAll(".switch-race");
  if (races.length && "IntersectionObserver" in window) {
    var raceObserver = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("is-visible");
        raceObserver.unobserve(entry.target);
      });
    }, { threshold: 0.6 });
    races.forEach(function (race) { raceObserver.observe(race); });
  }

  // ---------- Discord links ----------
  // Every documented Discord type ends its docstring with "Discord: <link>"; show it as a link to
  // that section rather than a raw URL.

  document.querySelectorAll(".prose p").forEach(function (paragraph) {
    var link = paragraph.querySelector("a[href^='https://docs.discord.com/']");
    if (!link || paragraph.textContent.trim().indexOf("Discord:") !== 0) return;
    var anchor = link.hash ? decodeURIComponent(link.hash.slice(1)) : "";
    var page = link.pathname.replace(/\/$/, "").split("/").pop();
    var section = (anchor || page).replace(/-/g, " ");
    link.textContent = section;
    paragraph.classList.add("discord-ref");
    paragraph.firstChild.textContent = "Discord docs: ";
  });

  // ---------- Mobile menu ----------

  var navToggle = document.querySelector("[data-nav-toggle]");
  var navBody = document.querySelector("[data-nav-body]");
  if (navToggle && navBody) {
    navToggle.addEventListener("click", function () {
      var open = navBody.classList.toggle("is-open");
      navToggle.setAttribute("aria-expanded", String(open));
    });
  }

  // ---------- Contents highlight ----------

  var tocLinks = Array.prototype.slice.call(document.querySelectorAll(".doc-toc a"));
  if (tocLinks.length && "IntersectionObserver" in window) {
    var byId = {};
    tocLinks.forEach(function (link) { byId[decodeURIComponent(link.hash.slice(1))] = link; });
    var visible = new Set();
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) visible.add(entry.target.id); else visible.delete(entry.target.id);
      });
      var current = null;
      tocLinks.forEach(function (link) {
        var id = decodeURIComponent(link.hash.slice(1));
        if (!current && visible.has(id)) current = link;
      });
      if (current) {
        tocLinks.forEach(function (link) { link.classList.toggle("is-current", link === current); });
      }
    }, { rootMargin: "-64px 0px -60% 0px" });
    Object.keys(byId).forEach(function (id) {
      var heading = document.getElementById(id);
      if (heading) observer.observe(heading);
    });
  }

  // ---------- Search ----------

  var dialog = document.querySelector("[data-search]");
  var input = document.querySelector("[data-search-input]");
  var results = document.querySelector("[data-search-results]");
  var empty = document.querySelector("[data-search-empty]");
  var index = null;
  var selected = -1;
  var lastFocus = null;

  function loadIndex() {
    if (index) return Promise.resolve(index);
    return fetch(window.SHOAL_BASE + "/search/search_index.json")
      .then(function (response) { return response.json(); })
      .then(function (data) {
        index = data.docs.map(function (doc) {
          return {
            location: doc.location,
            title: doc.title,
            text: doc.text,
            haystack: (doc.title + " " + doc.text).toLowerCase(),
            titleLower: doc.title.toLowerCase(),
          };
        });
        return index;
      });
  }

  function pageTitle(location) {
    var page = location.split("#")[0].replace(/\/$/, "");
    if (!page) return "Home";
    var parts = page.split("/");
    if (parts[0] === "reference") return parts.slice(1).join(".");
    return parts[parts.length - 1].replace(/-/g, " ");
  }

  function score(doc, terms) {
    var total = 0;
    for (var i = 0; i < terms.length; i++) {
      var term = terms[i];
      if (doc.haystack.indexOf(term) === -1) return 0;
      if (doc.titleLower === term) total += 40;
      else if (doc.titleLower.indexOf(term) === 0) total += 20;
      else if (doc.titleLower.indexOf(term) !== -1) total += 10;
      else total += 1;
    }
    if (doc.location.indexOf("#") === -1) total += 2;
    if (doc.location.indexOf("reference/") !== 0) total += 3;
    return total;
  }

  function excerpt(text, term) {
    var plain = text.replace(/<[^>]+>/g, "").replace(/(Discord: )?https?:\/\/\S+/g, "").replace(/¶/g, "").replace(/\s+/g, " ").trim();
    var at = plain.toLowerCase().indexOf(term);
    if (at === -1) return plain.slice(0, 110);
    var start = Math.max(0, at - 40);
    return (start > 0 ? "…" : "") + plain.slice(start, start + 120);
  }

  function render(query) {
    var terms = query.toLowerCase().split(/\s+/).filter(Boolean);
    results.textContent = "";
    selected = -1;
    if (!terms.length) { empty.hidden = true; return; }
    var matches = index
      .map(function (doc) { return { doc: doc, score: score(doc, terms) }; })
      .filter(function (match) { return match.score > 0; })
      .sort(function (a, b) { return b.score - a.score; })
      .slice(0, 12);
    empty.hidden = matches.length > 0;
    matches.forEach(function (match) {
      var item = document.createElement("li");
      var link = document.createElement("a");
      link.href = window.SHOAL_BASE + "/" + match.doc.location;
      var title = document.createElement("strong");
      title.textContent = match.doc.title.replace(/<[^>]+>/g, "");
      var where = document.createElement("span");
      where.textContent = pageTitle(match.doc.location);
      var snippet = document.createElement("small");
      snippet.textContent = excerpt(match.doc.text, terms[0]);
      link.append(title, where, snippet);
      link.addEventListener("click", closeSearch);
      item.appendChild(link);
      results.appendChild(item);
    });
  }

  function highlight(next) {
    var links = results.querySelectorAll("a");
    if (!links.length) return;
    selected = (next + links.length) % links.length;
    links.forEach(function (link, i) { link.setAttribute("aria-selected", String(i === selected)); });
    links[selected].scrollIntoView({ block: "nearest" });
  }

  function openSearch() {
    lastFocus = document.activeElement;
    dialog.hidden = false;
    input.value = "";
    results.textContent = "";
    empty.hidden = true;
    input.focus();
    loadIndex();
  }

  function closeSearch() {
    dialog.hidden = true;
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }

  if (dialog) {
    document.querySelectorAll("[data-search-open]").forEach(function (button) {
      button.addEventListener("click", openSearch);
    });
    dialog.addEventListener("click", function (event) { if (event.target === dialog) closeSearch(); });
    input.addEventListener("input", function () {
      loadIndex().then(function () { render(input.value); });
    });
    input.addEventListener("keydown", function (event) {
      if (event.key === "ArrowDown") { event.preventDefault(); highlight(selected + 1); }
      else if (event.key === "ArrowUp") { event.preventDefault(); highlight(selected - 1); }
      else if (event.key === "Enter") {
        var links = results.querySelectorAll("a");
        var target = links[selected >= 0 ? selected : 0];
        if (target) { closeSearch(); window.location.href = target.href; }
      }
    });
    document.addEventListener("keydown", function (event) {
      var typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName);
      if (event.key === "/" && !typing && dialog.hidden) { event.preventDefault(); openSearch(); }
      else if ((event.key === "k" || event.key === "K") && (event.metaKey || event.ctrlKey)) { event.preventDefault(); openSearch(); }
      else if (event.key === "Escape" && !dialog.hidden) closeSearch();
    });
  }
})();
