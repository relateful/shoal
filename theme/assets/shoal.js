// Shoal docs: theme switching, search, copy buttons, the mobile menu, the contents highlight and
// the school of fish on the home page. No dependencies.
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

  // ---------- The school ----------
  // A small flocking simulation: each fish steers with its neighbours (stay close, swim the same
  // way, do not collide) and drifts towards the open water beside the headline.

  var canvas = document.querySelector("[data-school]");
  if (canvas && canvas.getContext) startSchool(canvas);

  function startSchool(canvas) {
    var context = canvas.getContext("2d");
    var fish = [];
    var width = 0, height = 0, ratio = 1;
    var pointer = { x: -1e4, y: -1e4 };
    var colour = "";
    var running = false;
    var onScreen = true;
    var clock = 0;
    var last = null;
    var faint = false;

    function readColour() {
      colour = getComputedStyle(root).getPropertyValue("--fish").trim();
    }

    function resize() {
      var box = canvas.getBoundingClientRect();
      ratio = Math.min(window.devicePixelRatio || 1, 2);
      width = box.width;
      height = box.height;
      canvas.width = Math.round(width * ratio);
      canvas.height = Math.round(height * ratio);
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      // Fewer, fainter fish on narrow screens, where they share the space with the text.
      faint = width < 900;
      var wanted = Math.round(Math.min(120, Math.max(faint ? 28 : 40, (width * height) / (faint ? 14000 : 9000))));
      while (fish.length < wanted) fish.push(spawn());
      fish.length = wanted;
    }

    function spawn() {
      var angle = Math.random() * Math.PI * 2;
      return {
        x: width * (0.45 + Math.random() * 0.55),
        y: Math.random() * height,
        vx: Math.cos(angle) * 1.2,
        vy: Math.sin(angle) * 1.2,
        size: 9 + Math.random() * 7,
        depth: 0.35 + Math.random() * 0.65,
      };
    }

    function step(scale) {
      // `scale` is elapsed time in 60 Hz frames: forces and movement are applied in proportion.
      scale = scale || 1;
      // Beside the headline on wide screens; below the text on narrow ones, so it stays readable.
      var wide = width > 900;
      var homeX = wide ? width * 0.72 : width * 0.6;
      var homeY = wide ? height * 0.5 : height * 0.9;
      for (var i = 0; i < fish.length; i++) {
        var a = fish[i];
        var cx = 0, cy = 0, ax = 0, ay = 0, sx = 0, sy = 0, near = 0;
        for (var j = 0; j < fish.length; j++) {
          if (i === j) continue;
          var b = fish[j];
          var dx = b.x - a.x, dy = b.y - a.y;
          var d2 = dx * dx + dy * dy;
          if (d2 < 8100) {
            cx += b.x; cy += b.y; ax += b.vx; ay += b.vy; near++;
            if (d2 < 484) { sx -= dx / (d2 + 1); sy -= dy / (d2 + 1); }
          }
        }
        if (near) {
          a.vx += (((cx / near - a.x) * 0.0022) + ((ax / near - a.vx) * 0.06)) * scale;
          a.vy += (((cy / near - a.y) * 0.0022) + ((ay / near - a.vy) * 0.06)) * scale;
        }
        a.vx += (sx * 1.4 + (homeX - a.x) * 0.00008) * scale;
        a.vy += (sy * 1.4 + (homeY - a.y) * 0.00012) * scale;

        var px = a.x - pointer.x, py = a.y - pointer.y;
        var p2 = px * px + py * py;
        if (p2 < 14400) {
          a.vx += (px / Math.sqrt(p2 + 1)) * 0.35 * scale;
          a.vy += (py / Math.sqrt(p2 + 1)) * 0.35 * scale;
        }

        var speed = Math.sqrt(a.vx * a.vx + a.vy * a.vy);
        var max = 2.1 * a.depth + 0.5, min = 0.7;
        if (speed > max) { a.vx *= max / speed; a.vy *= max / speed; }
        else if (speed < min) { a.vx *= min / (speed || 1); a.vy *= min / (speed || 1); }

        a.x += a.vx * scale; a.y += a.vy * scale;
        if (a.x < -20) a.x = width + 20; else if (a.x > width + 20) a.x = -20;
        if (a.y < -20) a.y = height + 20; else if (a.y > height + 20) a.y = -20;
      }
    }

    function draw() {
      context.clearRect(0, 0, width, height);
      for (var i = 0; i < fish.length; i++) {
        var f = fish[i];
        var angle = Math.atan2(f.vy, f.vx);
        var tail = Math.sin(clock * 0.015 + i) * 0.35;
        context.save();
        context.translate(f.x, f.y);
        context.rotate(angle);
        var alpha = (0.14 + f.depth * 0.3) * (faint ? 0.55 : 1);
        context.fillStyle = "rgba(" + colour + "," + alpha.toFixed(3) + ")";
        var s = f.size * (0.55 + f.depth * 0.45);
        context.beginPath();
        context.moveTo(s, 0);
        context.quadraticCurveTo(0, -s * 0.42, -s * 0.85, 0);
        context.lineTo(-s * 1.35, -s * (0.35 + tail * 0.4));
        context.lineTo(-s * 1.2, 0);
        context.lineTo(-s * 1.35, s * (0.35 - tail * 0.4));
        context.lineTo(-s * 0.85, 0);
        context.quadraticCurveTo(0, s * 0.42, s, 0);
        context.fill();
        context.restore();
      }
    }

    function loop(now) {
      if (!running) return;
      // Clamp long gaps (a background tab, a slow frame) so the school never jumps.
      var elapsed = last === null ? 16.667 : Math.min(now - last, 50);
      last = now;
      clock += elapsed;
      step(elapsed / 16.667);
      draw();
      requestAnimationFrame(loop);
    }

    function play() {
      if (running || reducedMotion.matches || !onScreen || document.hidden) return;
      running = true;
      last = null;
      requestAnimationFrame(loop);
    }

    function pause() { running = false; }

    function still() {
      // Reduced motion: settle the school, then draw it once.
      for (var i = 0; i < 240; i++) step();
      draw();
    }

    readColour();
    resize();
    // Start from a school that has already formed, not a scatter that takes seconds to gather.
    for (var warm = 0; warm < 180; warm++) step();
    draw();  // visible even if the page starts in a background tab, before any frame runs
    if (reducedMotion.matches) still(); else play();

    window.addEventListener("resize", function () { resize(); if (!running) draw(); });
    document.addEventListener("shoal:theme", function () { readColour(); if (!running) draw(); });
    document.addEventListener("visibilitychange", function () { if (document.hidden) pause(); else play(); });
    reducedMotion.addEventListener("change", function () { if (reducedMotion.matches) { pause(); still(); } else play(); });
    canvas.parentElement.addEventListener("pointermove", function (event) {
      var box = canvas.getBoundingClientRect();
      pointer.x = event.clientX - box.left;
      pointer.y = event.clientY - box.top;
    });
    canvas.parentElement.addEventListener("pointerleave", function () { pointer.x = pointer.y = -1e4; });
    if ("IntersectionObserver" in window) {
      new IntersectionObserver(function (entries) {
        onScreen = entries[0].isIntersecting;
        if (onScreen) play(); else pause();
      }).observe(canvas);
    }
  }
})();
