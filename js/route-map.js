(() => {
  if (!window.L) return;

  function create(canvas) {
    const map = L.map(canvas, { scrollWheelZoom: false, worldCopyJump: true }).setView([53, -2.5], 6);
    const routeLine = L.polyline([], { color: "#156753", weight: 5, opacity: 0.9, interactive: false }).addTo(map);
    const markers = L.layerGroup().addTo(map);
    const tiles = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      maxZoom: 19,
      referrerPolicy: "strict-origin-when-cross-origin",
    });

    // Fetch map tiles only when the map is near view.
    if (window.IntersectionObserver) {
      const observer = new IntersectionObserver(([entry]) => {
        if (entry.isIntersecting) {
          tiles.addTo(map);
          observer.disconnect();
        }
      }, { rootMargin: "200px" });
      observer.observe(canvas);
    } else {
      tiles.addTo(map);
    }

    function setStops(stops) {
      markers.clearLayers();
      stops.forEach((stop) => {
        const title = stop.title || `Stop ${stop.number}`;
        const icon = L.divIcon({
          className: "geographic-map__pin",
          html: String(stop.number),
          iconSize: [28, 28],
          iconAnchor: [14, 14],
          popupAnchor: [0, -14],
        });
        const label = document.createElement("span");
        label.textContent = title;
        L.marker(stop.position, { icon, title }).bindPopup(label).addTo(markers);
      });
    }

    function fit(track, stops) {
      const points = track.flat().concat(stops.map((stop) => stop.position));
      if (points.length) map.fitBounds(points, { padding: [24, 24], maxZoom: 14, animate: false });
    }

    return {
      map,
      setTrack: (track) => routeLine.setLatLngs(track),
      setStops,
      fit,
    };
  }

  window.EA600RouteMap = { create };

  document.querySelectorAll("[data-geographic-route]").forEach((root) => {
    const { track, stops } = JSON.parse(root.querySelector('script[type="application/json"]').textContent);
    const route = create(root.querySelector("[data-map-canvas]"));
    route.setTrack(track);
    route.setStops(stops);
    route.fit(track, stops);
  });
})();
