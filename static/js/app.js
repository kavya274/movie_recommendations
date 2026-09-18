/* ---------------------------------------------------------------------------
   Progressive enhancement.

   Every feature here has a server-rendered fallback: the library toggles are
   real form posts, the search palette is a real GET form, the genre chips and
   tabs are real links. Nothing below is load-bearing — with JavaScript off the
   site still works, it just does a round trip.
--------------------------------------------------------------------------- */

(function () {
  "use strict";

  const $ = (selector, root) => (root || document).querySelector(selector);
  const $$ = (selector, root) => Array.from((root || document).querySelectorAll(selector));

  /* -- Poster fade ------------------------------------------------------- */
  /* A cached image can finish decoding before this script runs, so the inline
     onload never fires. Catch those up here. */

  function markLoadedPosters() {
    $$(".poster img").forEach((img) => {
      if (img.complete && img.naturalWidth > 0) img.classList.add("is-loaded");
    });
  }

  /* -- Header ------------------------------------------------------------ */
  /* Transparent over the hero, solid once the page moves. */

  function initHeader() {
    const header = $("[data-header]");
    if (!header) return;

    const sync = () => header.classList.toggle("is-scrolled", window.scrollY > 12);
    sync();
    window.addEventListener("scroll", sync, { passive: true });

    const toggle = $("[data-menu-toggle]");
    const nav = $("[data-mobile-nav]");
    if (toggle && nav) {
      toggle.addEventListener("click", () => {
        const open = nav.hasAttribute("hidden");
        nav.toggleAttribute("hidden", !open);
        toggle.setAttribute("aria-expanded", String(open));
        toggle.setAttribute("aria-label", open ? "Close menu" : "Open menu");
        header.classList.toggle("is-open", open);
      });
    }
  }

  /* -- Profile menu ------------------------------------------------------ */

  function initProfileMenu() {
    const container = $("[data-profile]");
    const toggle = $("[data-profile-toggle]");
    const menu = $("[data-profile-menu]");
    if (!container || !toggle || !menu) return;

    const close = () => {
      menu.setAttribute("hidden", "");
      toggle.setAttribute("aria-expanded", "false");
    };

    toggle.addEventListener("click", (event) => {
      event.stopPropagation();
      const opening = menu.hasAttribute("hidden");
      menu.toggleAttribute("hidden", !opening);
      toggle.setAttribute("aria-expanded", String(opening));
    });

    document.addEventListener("mousedown", (event) => {
      if (!container.contains(event.target)) close();
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") close();
    });
  }

  /* -- Rails ------------------------------------------------------------- */
  /* Arrows page the scroller; they disable at either end. */

  function initRails() {
    $$("[data-rail-track]").forEach((track) => {
      const rail = track.closest(".rail");
      const prev = $("[data-rail-prev]", rail);
      const next = $("[data-rail-next]", rail);
      if (!prev || !next) return;

      const sync = () => {
        const max = track.scrollWidth - track.clientWidth;
        prev.disabled = track.scrollLeft <= 8;
        next.disabled = track.scrollLeft >= max - 8;
      };

      const page = (direction) => {
        track.scrollBy({ left: direction * track.clientWidth * 0.85, behavior: "smooth" });
      };

      prev.addEventListener("click", () => page(-1));
      next.addEventListener("click", () => page(1));
      track.addEventListener("scroll", sync, { passive: true });

      if (window.ResizeObserver) new ResizeObserver(sync).observe(track);
      sync();
    });
  }

  /* -- Library toggles --------------------------------------------------- */
  /* Intercepts the watched / watchlist form posts and applies the server's
     answer in place, so a click never scrolls the page back to the top. */

  const ICON = {
    plus: "#i-plus",
    check: "#i-check",
    eye: "#i-eye",
    bookmark: "#i-bookmark",
    bookmarkFilled: "#i-bookmark-filled",
  };

  function setIcon(button, href, solid) {
    const use = $("use", button);
    if (!use) return;
    use.setAttribute("href", href);
    const svg = use.closest("svg");
    if (svg) svg.classList.toggle("icon-solid", Boolean(solid));
  }

  function updateButton(form, state) {
    const button = $("button[type=submit]", form);
    if (!button) return;

    const isWatchedAction = form.action.indexOf("/library/watched/") !== -1;
    const label = $("span", button);
    const card = form.closest(".card");
    const title = card ? $(".card-title", card)?.textContent?.trim() : null;

    if (isWatchedAction) {
      button.setAttribute("aria-pressed", String(state.watched));
      setIcon(button, state.watched ? ICON.check : ICON.eye, false);
      if (label) label.textContent = state.watched ? "Watched" : "Mark as watched";
      button.classList.toggle("btn-secondary", state.watched);
      button.classList.toggle("btn-outline", !state.watched);
    } else {
      button.setAttribute("aria-pressed", String(state.watchlist));
      const quick = button.classList.contains("quick-add");
      if (quick) {
        setIcon(button, state.watchlist ? ICON.check : ICON.plus, false);
      } else {
        setIcon(button, state.watchlist ? ICON.bookmarkFilled : ICON.bookmark, state.watchlist);
        if (label) label.textContent = state.watchlist ? "In watchlist" : "Watchlist";
        button.classList.toggle("btn-secondary", state.watchlist);
        button.classList.toggle("btn-outline", !state.watchlist);
      }
      if (title) {
        button.setAttribute(
          "aria-label",
          (state.watchlist ? "Remove " : "Add ") + title + (state.watchlist ? " from watchlist" : " to watchlist")
        );
      }
    }

    // Marking something watched clears it from the watchlist, so every card for
    // this movie has to follow — including the one in another rail.
    syncCards(state);
  }

  function syncCards(state) {
    $$('[data-library-form][data-slug="' + state.id + '"]').forEach((form) => {
      const card = form.closest(".card");
      if (!card) return;

      const art = $(".card-art", card);
      let badge = $("[data-watched-badge]", art);
      if (state.watched && !badge) {
        badge = document.createElement("span");
        badge.className = "badge badge-watched";
        badge.setAttribute("data-watched-badge", "");
        badge.title = "You've watched this";
        badge.innerHTML = '<svg class="icon icon-sm"><use href="#i-check"></use></svg>Watched';
        art.prepend(badge);
      } else if (!state.watched && badge) {
        badge.remove();
      }

      const quick = $(".quick-add", form);
      if (quick) {
        quick.setAttribute("aria-pressed", String(state.watchlist));
        setIcon(quick, state.watchlist ? ICON.check : ICON.plus, false);
      }
    });
  }

  function updateCounts(state) {
    const watched = $("[data-count-watched]");
    const watchlist = $("[data-count-watchlist]");
    if (watched) watched.textContent = state.watchedCount;
    if (watchlist) watchlist.textContent = state.watchlistCount;
  }

  function initLibraryForms() {
    document.addEventListener("submit", async (event) => {
      const form = event.target.closest("[data-library-form]");
      if (!form) return;

      event.preventDefault();
      const button = $("button[type=submit]", form);
      if (button) button.disabled = true;

      try {
        const response = await fetch(form.action, {
          method: "POST",
          body: new FormData(form),
          headers: { "X-Requested-With": "fetch", Accept: "application/json" },
          credentials: "same-origin",
        });
        if (!response.ok) throw new Error("Request failed: " + response.status);

        const state = await response.json();
        updateButton(form, state);
        updateCounts(state);
      } catch (error) {
        // Fall back to the plain form post rather than silently doing nothing.
        form.submit();
        return;
      } finally {
        if (button) button.disabled = false;
      }
    });
  }

  /* -- Search palette ---------------------------------------------------- */

  function initSearch() {
    const dialog = $("[data-search-dialog]");
    const input = $("[data-search-input]");
    const list = $("[data-search-list]");
    const hint = $("[data-search-hint]");
    if (!dialog || !input || !list) return;

    const endpoint = dialog.dataset.searchUrl || "/api/search/";
    const staticRoot = dialog.dataset.staticUrl || "/static/";
    let controller = null;
    let debounce = null;
    let previousOverflow = "";

    const open = () => {
      dialog.removeAttribute("hidden");
      previousOverflow = document.body.style.overflow;
      document.body.style.overflow = "hidden";
      window.setTimeout(() => input.focus(), 30);
      if (!list.childElementCount) run("");
    };

    const close = () => {
      dialog.setAttribute("hidden", "");
      document.body.style.overflow = previousOverflow;
      input.value = "";
    };

    async function run(query) {
      if (controller) controller.abort();
      controller = new AbortController();

      try {
        const url = endpoint + "?q=" + encodeURIComponent(query) + "&limit=10";
        const response = await fetch(url, { signal: controller.signal, credentials: "same-origin" });
        if (!response.ok) return;
        const data = await response.json();
        render(data.results, query);
      } catch (error) {
        if (error.name !== "AbortError") list.innerHTML = '<p class="search-empty">Search is unavailable.</p>';
      }
    }

    function render(results, query) {
      if (hint) hint.textContent = query ? "Results" : "Top rated";

      if (!results.length) {
        list.innerHTML = '<p class="search-empty">No movies match "' + escapeHtml(query) + '".</p>';
        return;
      }

      list.innerHTML = results
        .map(
          (movie) =>
            '<a class="search-result" data-result href="' +
            movie.url +
            '">' +
            '<span class="thumb"><img src="' + staticRoot +
            escapeHtml(movie.poster) +
            '" alt="" loading="lazy"></span>' +
            '<span class="info"><span class="name">' +
            escapeHtml(movie.title) +
            (movie.watched ? " ✓" : "") +
            '</span><span class="sub">' +
            movie.year +
            " · " +
            escapeHtml(movie.genre) +
            "</span></span>" +
            '<span class="score">' +
            movie.rating.toFixed(1) +
            "</span></a>"
        )
        .join("");
    }

    $$("[data-search-open]").forEach((trigger) => trigger.addEventListener("click", open));
    $$("[data-search-close]").forEach((trigger) => trigger.addEventListener("click", close));

    input.addEventListener("input", () => {
      window.clearTimeout(debounce);
      const query = input.value;
      debounce = window.setTimeout(() => run(query), 150);
    });

    // Arrow keys walk the result list; Escape always closes.
    dialog.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        close();
        return;
      }
      if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;

      const links = $$("a[data-result]", list);
      if (!links.length) return;
      event.preventDefault();

      const index = links.indexOf(document.activeElement);
      let next;
      if (event.key === "ArrowDown") {
        next = links[Math.min(index + 1, links.length - 1)] || links[0];
      } else {
        next = index <= 0 ? input : links[index - 1];
      }
      if (next) next.focus();
    });

    // "/" and Cmd/Ctrl+K open search, as long as the user isn't typing already.
    document.addEventListener("keydown", (event) => {
      const target = event.target;
      const typing =
        target &&
        (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable);
      if (typing) return;

      if (event.key === "/" || ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k")) {
        event.preventDefault();
        open();
      }
    });
  }

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (char) => {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char];
    });
  }

  /* -- Misc -------------------------------------------------------------- */

  function initAutoSubmit() {
    $$("[data-autosubmit] select").forEach((select) => {
      select.addEventListener("change", () => select.form.submit());
    });
  }

  function initMessages() {
    const container = $("[data-messages]");
    if (!container) return;
    window.setTimeout(() => {
      container.style.transition = "opacity 0.3s";
      container.style.opacity = "0";
      window.setTimeout(() => container.remove(), 300);
    }, 3200);
  }

  function init() {
    markLoadedPosters();
    initHeader();
    initProfileMenu();
    initRails();
    initLibraryForms();
    initSearch();
    initAutoSubmit();
    initMessages();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
