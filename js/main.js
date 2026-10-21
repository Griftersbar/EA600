function initMobileNav(root = document) {
  const toggle = root.querySelector("[data-nav-toggle]");
  const nav = root.querySelector("#primary-nav");
  if (!toggle || !nav) return;

  toggle.addEventListener("click", () => {
    const open = nav.classList.toggle("is-open");
    toggle.setAttribute("aria-expanded", String(open));
    toggle.setAttribute("aria-label", open ? "Close menu" : "Open menu");
  });

  nav.querySelectorAll("a").forEach((link) => {
    link.addEventListener("click", () => {
      nav.classList.remove("is-open");
      toggle.setAttribute("aria-expanded", "false");
      toggle.setAttribute("aria-label", "Open menu");
    });
  });
}

function initNavScrollSpy() {
  const links = [...document.querySelectorAll("[data-nav-link]")];
  if (!links.length) return;

  const sections = links
    .map((link) => {
      const id = link.getAttribute("href").slice(1);
      const el =
        id === "top" ? document.querySelector(".hero") : document.getElementById(id);
      return el ? { id, el, link } : null;
    })
    .filter(Boolean);

  const setActive = (id) => {
    links.forEach((link) => {
      const href = link.getAttribute("href");
      const active = href === `#${id}`;
      link.classList.toggle("is-active", active);
      if (active) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    });
  };

  const observer = new IntersectionObserver(
    (entries) => {
      const visible = entries
        .filter((entry) => entry.isIntersecting)
        .sort((a, b) => b.intersectionRatio - a.intersectionRatio);
      if (!visible.length) return;
      const match = sections.find((section) => section.el === visible[0].target);
      if (match) setActive(match.id);
    },
    { rootMargin: "-45% 0px -50% 0px", threshold: [0, 0.15, 0.35] }
  );

  sections.forEach((section) => observer.observe(section.el));

  if (window.scrollY < 80) setActive("top");
}

function faqPrefersReducedMotion() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function faqSetTriggerExpanded(trigger, open) {
  if (!trigger) return;
  trigger.setAttribute("aria-expanded", String(open));
}

function faqSetPanelOpen(panel, trigger, open) {
  panel.classList.toggle("is-open", open);
  faqSetTriggerExpanded(trigger, open);
  if (open) panel.removeAttribute("hidden");
  else panel.setAttribute("hidden", "");
}

const FAQ_COLLAPSE_MS = 350;

function faqAnimatePanel(panel, open) {
  if (faqPrefersReducedMotion()) {
    return Promise.resolve();
  }

  return new Promise((resolve) => {
    let settled = false;
    let fallbackId;

    const cleanup = () => {
      panel.classList.remove("is-collapsing");
      panel.style.height = "";
      if (open) panel.classList.add("is-open");
      else panel.setAttribute("hidden", "");
    };

    const finish = () => {
      if (settled) return;
      settled = true;
      panel.removeEventListener("transitionend", onEnd);
      clearTimeout(fallbackId);
      cleanup();
      resolve();
    };

    panel.classList.add("is-collapsing");

    if (open) {
      panel.removeAttribute("hidden");
      panel.style.height = "0px";
      panel.offsetHeight;
      panel.style.height = `${panel.scrollHeight}px`;
    } else {
      panel.style.height = `${panel.scrollHeight}px`;
      panel.offsetHeight;
      panel.classList.remove("is-open");
      panel.style.height = "0px";
    }

    const onEnd = (event) => {
      if (event.target !== panel || event.propertyName !== "height") return;
      finish();
    };

    panel.addEventListener("transitionend", onEnd);
    fallbackId = setTimeout(finish, FAQ_COLLAPSE_MS + 80);
  });
}

function initFaqAccordion(root = document) {
  const list = root.querySelector("[data-faq-accordion]");
  if (!list) return;

  const items = [...list.querySelectorAll(".faq-item")];
  let busy = false;

  items.forEach((item) => {
    const trigger = item.querySelector(".faq-item__trigger");
    const panel = item.querySelector(".faq-item__collapse");
    if (!trigger || !panel) return;

    if (panel.classList.contains("is-open")) {
      faqSetPanelOpen(panel, trigger, true);
    } else {
      faqSetPanelOpen(panel, trigger, false);
    }

    trigger.addEventListener("click", async () => {
      if (busy) return;

      const isOpen = panel.classList.contains("is-open");

      busy = true;
      try {
        if (isOpen) {
          faqSetTriggerExpanded(trigger, false);
          await faqAnimatePanel(panel, false);
          faqSetPanelOpen(panel, trigger, false);
          return;
        }

        const openItems = items.filter(
          (other) =>
            other !== item &&
            other.querySelector(".faq-item__collapse")?.classList.contains("is-open")
        );

        openItems.forEach((other) => {
          faqSetTriggerExpanded(other.querySelector(".faq-item__trigger"), false);
        });
        faqSetTriggerExpanded(trigger, true);

        const closeOthers = openItems.map(async (other) => {
          const otherPanel = other.querySelector(".faq-item__collapse");
          const otherTrigger = other.querySelector(".faq-item__trigger");
          if (!otherPanel || !otherTrigger) return;
          await faqAnimatePanel(otherPanel, false);
          faqSetPanelOpen(otherPanel, otherTrigger, false);
        });

        await Promise.all([...closeOthers, faqAnimatePanel(panel, true)]);
        faqSetPanelOpen(panel, trigger, true);
      } finally {
        busy = false;
      }
    });
  });
}

const FOOTER_LINK_ARROW_MS = 600;

function initFooterLinkHover(root = document) {
  const links = [...root.querySelectorAll(".site-footer__link-list a")];
  if (!links.length) return;

  links.forEach((link) => {
    let hoverFrame = null;
    let collapseTimer = null;

    const setHover = (active) => {
      cancelAnimationFrame(hoverFrame);
      hoverFrame = requestAnimationFrame(() => {
        link.classList.toggle("is-hover", active);
        clearTimeout(collapseTimer);

        const arrow = link.querySelector(".site-footer__link-arrow");
        if (!arrow) return;

        if (active) {
          arrow.classList.add("is-open");
          return;
        }

        collapseTimer = setTimeout(() => {
          arrow.classList.remove("is-open");
        }, FOOTER_LINK_ARROW_MS);
      });
    };

    link.addEventListener("mouseenter", () => setHover(true), { passive: true });
    link.addEventListener("mouseleave", () => setHover(false), { passive: true });
    link.addEventListener("focus", () => setHover(true), true);
    link.addEventListener("blur", () => setHover(false), true);
  });
}

// Adds the scrolled style to the sticky header after it passes its sentinel.
function initHeaderScroll() {
  const header = document.querySelector("[data-site-header]");
  if (!header) return;

  const scrollOffset = 48;
  const setScrolled = (scrolled) => header.classList.toggle("is-scrolled", scrolled);
  const readScrollTop = () =>
    window.scrollY ||
    window.pageYOffset ||
    document.documentElement.scrollTop ||
    document.body.scrollTop ||
    0;
  const syncFromScroll = () => setScrolled(readScrollTop() > scrollOffset);

  let sentinel = document.querySelector("[data-header-scroll-sentinel]");
  if (!sentinel) {
    sentinel = document.createElement("div");
    sentinel.className = "site-header__scroll-sentinel";
    sentinel.setAttribute("data-header-scroll-sentinel", "");
    sentinel.setAttribute("aria-hidden", "true");
    header.insertAdjacentElement("afterend", sentinel);
  }

  if ("IntersectionObserver" in window) {
    const observer = new IntersectionObserver(([entry]) => {
      if (entry) setScrolled(!entry.isIntersecting);
    });
    observer.observe(sentinel);
  }

  syncFromScroll();
  window.addEventListener("scroll", syncFromScroll, { passive: true });
  window.addEventListener("resize", syncFromScroll, { passive: true });
  window.addEventListener("load", syncFromScroll, { passive: true });
}

// Adds responsive card-slider controls and optional autoplay for marked tracks.
function initCardSliders() {
  const sliderQuery = "(max-width: 60.75rem)";
  const sliderMq = window.matchMedia(sliderQuery);
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

  function arrowIcon(direction) {
    const isPrev = direction === "prev";
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("width", "16");
    svg.setAttribute("height", "16");
    svg.setAttribute("viewBox", "0 0 16 16");
    svg.setAttribute("fill", "none");
    svg.setAttribute("aria-hidden", "true");
    svg.classList.add("card-slider-nav__icon");

    const line = document.createElementNS("http://www.w3.org/2000/svg", "path");
    line.setAttribute("d", isPrev ? "M12.666 8H3.334" : "M3.334 8H12.666");
    line.setAttribute("stroke", "currentColor");
    line.setAttribute("stroke-linecap", "round");
    line.setAttribute("stroke-linejoin", "round");

    const head = document.createElementNS("http://www.w3.org/2000/svg", "path");
    head.setAttribute(
      "d",
      isPrev ? "M8 3.334L3.333 8L8 12.666" : "M8 3.334L12.667 8L8 12.666"
    );
    head.setAttribute("stroke", "currentColor");
    head.setAttribute("stroke-linecap", "round");
    head.setAttribute("stroke-linejoin", "round");

    svg.append(line, head);
    return svg;
  }

  function scrollStep(track) {
    const slide = track.querySelector(":scope > *");
    if (!slide) return Math.max(track.clientWidth * 0.85, 200);
    const styles = getComputedStyle(track);
    const gap = Number.parseFloat(styles.columnGap || styles.gap) || 0;
    return slide.getBoundingClientRect().width + gap;
  }

  function syncNav(track, previous, next) {
    const maxScroll = track.scrollWidth - track.clientWidth;
    if (maxScroll <= 2) {
      previous.disabled = true;
      next.disabled = true;
      return;
    }
    previous.disabled = track.scrollLeft <= 2;
    next.disabled = track.scrollLeft >= maxScroll - 2;
  }

  function bindTrack(track) {
    if (track.dataset.cardSliderReady === "1") return;
    track.dataset.cardSliderReady = "1";

    const nav = document.createElement("div");
    nav.className = "card-slider-nav";
    nav.setAttribute("data-card-slider-nav", "");

    const previous = document.createElement("button");
    previous.type = "button";
    previous.className = "card-slider-nav__btn card-slider-nav__btn--prev";
    previous.setAttribute("aria-label", "Previous slide");
    previous.append(arrowIcon("prev"));

    const next = document.createElement("button");
    next.type = "button";
    next.className = "card-slider-nav__btn card-slider-nav__btn--next";
    next.setAttribute("aria-label", "Next slide");
    next.append(arrowIcon("next"));

    nav.append(previous, next);
    track.insertAdjacentElement("afterend", nav);
    let lastInteraction = 0;

    function advanceAutomatically() {
      const maxScroll = track.scrollWidth - track.clientWidth;
      const paused =
        !sliderMq.matches ||
        reduceMotion.matches ||
        document.hidden ||
        track.matches(":hover") ||
        track.contains(document.activeElement) ||
        Date.now() - lastInteraction < 5000;

      if (!track.hasAttribute("data-card-slider-autoplay") || paused || maxScroll <= 2) {
        return;
      }

      if (track.scrollLeft >= maxScroll - 2) {
        track.scrollTo({ left: 0, behavior: "smooth" });
      } else {
        track.scrollBy({ left: scrollStep(track), behavior: "smooth" });
      }
    }

    const update = () => {
      const active = sliderMq.matches;
      nav.hidden = !active;
      if (active) syncNav(track, previous, next);
    };

    previous.addEventListener("click", () => {
      track.scrollBy({ left: -scrollStep(track), behavior: "smooth" });
    });
    next.addEventListener("click", () => {
      track.scrollBy({ left: scrollStep(track), behavior: "smooth" });
    });
    track.addEventListener("scroll", () => syncNav(track, previous, next), { passive: true });
    track.addEventListener("pointerdown", () => {
      lastInteraction = Date.now();
    }, { passive: true });
    window.addEventListener("resize", update, { passive: true });
    sliderMq.addEventListener("change", update);
    window.setInterval(advanceAutomatically, 4000);

    update();
    syncNav(track, previous, next);
  }

  document.querySelectorAll("[data-card-slider]").forEach(bindTrack);
}

// Route-map helpers build the SVG path and align active stops with map progress.
const ROUTE_MAP_VIEWBOX = { width: 796, height: 531 };
const ROUTE_PATH_TENSION = 4.5;

function parseMapPercent(element, property) {
  const raw =
    element.style.getPropertyValue(property) ||
    getComputedStyle(element).getPropertyValue(property);
  const value = parseFloat(raw);
  return Number.isFinite(value) ? value : NaN;
}

function mapPointFromElement(element, width, height) {
  const mx = parseMapPercent(element, "--mx");
  const my = parseMapPercent(element, "--my");
  return { x: (mx / 100) * width, y: (my / 100) * height };
}

function collectOrderedRoutePoints(section, pins) {
  const { width, height } = ROUTE_MAP_VIEWBOX;
  const points = [];

  pins.forEach((pin, index) => {
    points.push(mapPointFromElement(pin, width, height));
    section
      .querySelectorAll(`.route-map-guide[data-segment="${index}"]`)
      .forEach((guide) => points.push(mapPointFromElement(guide, width, height)));
  });

  return points;
}

function ensurePinWaveLayers(pins) {
  pins.forEach((pin) => {
    if (pin.querySelector(".route-map-pin__waves")) return;

    const waves = document.createElement("span");
    waves.className = "route-map-pin__waves";
    waves.setAttribute("aria-hidden", "true");

    for (let index = 0; index < 3; index += 1) {
      const wave = document.createElement("span");
      wave.className = "route-map-pin__wave";
      waves.appendChild(wave);
    }

    pin.insertBefore(waves, pin.firstChild);
  });
}

function orientRouteGuides(section, pins) {
  const { width, height } = ROUTE_MAP_VIEWBOX;
  const entries = [];

  pins.forEach((pin, index) => {
    entries.push({ el: pin, ...mapPointFromElement(pin, width, height) });
    section
      .querySelectorAll(`.route-map-guide[data-segment="${index}"]`)
      .forEach((guide) => entries.push({ el: guide, ...mapPointFromElement(guide, width, height) }));
  });

  const count = entries.length;
  if (count < 3) return;

  entries.forEach((entry, index) => {
    if (!entry.el?.classList.contains("route-map-guide")) return;
    const previous = entries[(index - 1 + count) % count];
    const next = entries[(index + 1) % count];
    const angle = (Math.atan2(next.y - previous.y, next.x - previous.x) * 180) / Math.PI;
    entry.el.style.setProperty("--guide-angle", `${angle}deg`);
  });
}

function closedSmoothPathD(points, tension = ROUTE_PATH_TENSION) {
  const count = points.length;
  if (count < 2) return "";

  const get = (index) => points[(index + count) % count];
  let path = `M ${points[0].x.toFixed(1)} ${points[0].y.toFixed(1)}`;

  for (let index = 0; index < count; index += 1) {
    const p0 = get(index - 1);
    const p1 = get(index);
    const p2 = get(index + 1);
    const p3 = get(index + 2);
    const cp1x = p1.x + (p2.x - p0.x) / tension;
    const cp1y = p1.y + (p2.y - p0.y) / tension;
    const cp2x = p2.x - (p3.x - p1.x) / tension;
    const cp2y = p2.y - (p3.y - p1.y) / tension;
    path += ` C ${cp1x.toFixed(1)} ${cp1y.toFixed(1)}, ${cp2x.toFixed(1)} ${cp2y.toFixed(1)}, ${p2.x.toFixed(1)} ${p2.y.toFixed(1)}`;
  }

  return path;
}

function applyRoutePathD(section, path) {
  section.querySelectorAll(".route-map-path").forEach((pathElement) => {
    pathElement.setAttribute("d", path);
  });
}

function closestProgressOnPath(pathElement, targetX, targetY, samples = 400) {
  const total = pathElement.getTotalLength();
  let bestLength = 0;
  let bestDistance = Number.POSITIVE_INFINITY;

  for (let index = 0; index <= samples; index += 1) {
    const length = (total * index) / samples;
    const point = pathElement.getPointAtLength(length);
    const distance = (point.x - targetX) ** 2 + (point.y - targetY) ** 2;
    if (distance < bestDistance) {
      bestDistance = distance;
      bestLength = length;
    }
  }

  return bestLength / total;
}

function formatLegendMiles(milesText) {
  const match = (milesText ?? "").match(/([\d.]+)\s*miles?/i);
  if (!match) return milesText ?? "";
  return `${match[1]} mi`;
}

function parseStopDistance(raw) {
  const text = (raw ?? "").trim();
  if (!text) return { miles: "", driveTime: "", nextPlace: "" };
  const miles = text.match(/^([\d.]+\s*miles?)/i)?.[1] ?? text;
  const driveTime = text.match(/·\s*([^·]+?)\s+to\s+/i)?.[1]?.trim() ?? "";
  const nextPlace = text.match(/\s+to\s+(.+)$/i)?.[1]?.trim() ?? "";
  return { miles, driveTime, nextPlace };
}

function updateRouteUiFromCard(card, targets) {
  if (!card) return;

  const distanceRaw = card.querySelector(".stop-card__distance span")?.textContent ?? "";
  const { miles, driveTime, nextPlace } = parseStopDistance(distanceRaw);
  const place = card.dataset.place || "";

  if (targets.legendPlace) targets.legendPlace.textContent = place;
  if (targets.legendDistance) targets.legendDistance.textContent = formatLegendMiles(miles);
  if (targets.legendDrive) targets.legendDrive.textContent = driveTime || "—";
  if (targets.legendTo) targets.legendTo.textContent = nextPlace || "—";
}

// Connects stop-card scrolling to the active map pin, route drawing, and legend.
function initRouteMapScroll(root = document) {
  const section = root.querySelector("[data-route-section]");
  if (!section) return;

  const sortByStopIndex = (a, b) => Number(a.dataset.stopIndex) - Number(b.dataset.stopIndex);
  const cards = [...section.querySelectorAll(".stop-card[data-stop-index]")].sort(sortByStopIndex);
  const pins = [...section.querySelectorAll(".route-map-pin")].sort(sortByStopIndex);
  ensurePinWaveLayers(pins);
  const stopCount = pins.length;
  const drawPath = section.querySelector(".route-map-path--draw");
  const routeUiTargets = {
    legendPlace: section.querySelector("[data-route-legend-place]"),
    legendDistance: section.querySelector("[data-route-legend-distance]"),
    legendDrive: section.querySelector("[data-route-legend-drive]"),
    legendTo: section.querySelector("[data-route-legend-to]"),
  };

  if (!cards.length) return;

  let pathLength = 0;
  let stopProgress = [];

  function setActive(stopIndex) {
    cards.forEach((card) => {
      const id = Number(card.dataset.stopIndex);
      card.classList.toggle("stop-card--active", id === stopIndex);
    });

    pins.forEach((pin) => {
      const id = Number(pin.dataset.stopIndex);
      pin.classList.toggle("is-active", id === stopIndex);
      pin.classList.toggle("is-passed", id <= stopIndex);
    });

    const card = cards.find((item) => Number(item.dataset.stopIndex) === stopIndex);
    updateRouteUiFromCard(card, routeUiTargets);

    if (drawPath && pathLength > 0) {
      const progress = stopIndex >= stopCount ? 1 : (stopProgress[stopIndex - 1] ?? 0);
      drawPath.style.strokeDashoffset = String(pathLength * (1 - progress));
    }
  }

  const stopList = section.querySelector(".stop-list");
  const routeSliderMq = window.matchMedia("(max-width: 60.75rem)");

  function pickIndexFromScroll() {
    const horizontal = routeSliderMq.matches;
    const focus = horizontal ? window.innerWidth * 0.45 : window.innerHeight * 0.4;
    let bestStopIndex = 1;
    let bestDistance = Number.POSITIVE_INFINITY;

    cards.forEach((card) => {
      const rect = card.getBoundingClientRect();
      const center = horizontal ? rect.left + rect.width * 0.5 : rect.top + rect.height * 0.35;
      const distance = Math.abs(center - focus);
      if (distance < bestDistance) {
        bestDistance = distance;
        bestStopIndex = Number(card.dataset.stopIndex);
      }
    });

    setActive(bestStopIndex);
  }

  function initPath() {
    if (!drawPath) return;

    const path = closedSmoothPathD(collectOrderedRoutePoints(section, pins));
    if (path) applyRoutePathD(section, path);

    drawPath.removeAttribute("pathLength");
    pathLength = drawPath.getTotalLength();
    drawPath.style.strokeDasharray = String(pathLength);
    drawPath.style.strokeDashoffset = String(pathLength);

    const { width, height } = ROUTE_MAP_VIEWBOX;
    stopProgress = pins.map((pin) => {
      const { x, y } = mapPointFromElement(pin, width, height);
      if (Number.isNaN(x) || Number.isNaN(y)) return 0;
      return closestProgressOnPath(drawPath, x, y);
    });

    orientRouteGuides(section, pins);
    pickIndexFromScroll();
  }

  let scrollTicking = false;
  function onScroll() {
    if (scrollTicking) return;
    scrollTicking = true;
    requestAnimationFrame(() => {
      scrollTicking = false;
      if (section.classList.contains("is-route-inview")) pickIndexFromScroll();
    });
  }

  const sectionObserver = new IntersectionObserver(([entry]) => {
    const visible = entry.isIntersecting && entry.intersectionRatio > 0.08;
    section.classList.toggle("is-route-inview", visible);
    if (visible) pickIndexFromScroll();
  }, { threshold: [0, 0.08, 0.2, 0.5] });
  sectionObserver.observe(section);

  window.addEventListener("scroll", onScroll, { passive: true });
  window.addEventListener("resize", onScroll, { passive: true });
  stopList?.addEventListener("scroll", onScroll, { passive: true });
  routeSliderMq.addEventListener("change", pickIndexFromScroll);

  const mapImage = section.querySelector(".route-map-frame__img");
  if (mapImage && !mapImage.complete) {
    mapImage.addEventListener("load", initPath, { once: true });
  } else {
    initPath();
  }

  pickIndexFromScroll();
}

document.addEventListener("DOMContentLoaded", () => {
  initNavScrollSpy();
  initMobileNav();
  initFaqAccordion();
  initFooterLinkHover();
  initHeaderScroll();
  initCardSliders();
  initRouteMapScroll();
});
