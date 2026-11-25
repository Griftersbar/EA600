(() => {
  const panel = document.querySelector("[data-route-editor]");
  if (!panel) return;
  const form = panel.closest("form");
  const group = form.querySelector('[data-editor-group="stops"]');
  const canvas = panel.querySelector("[data-map-canvas]");
  const trackField = panel.querySelector('[name="route_track"]');
  const file = panel.querySelector("[data-gpx-file]");
  const importButton = panel.querySelector("[data-gpx-import]");
  const clearTrack = panel.querySelector("[data-gpx-clear]");
  const cancelButton = panel.querySelector("[data-cancel-placement]");
  const returnButton = panel.querySelector("[data-return-to-stop]");
  const status = panel.querySelector("[data-map-status]");
  const summary = panel.querySelector("[data-track-summary]");
  const visibleRows = () => [...group.querySelectorAll("[data-row]:not([hidden])")];
  const coordinateInputs = (row) => [
    row.querySelector('[name$="-latitude"]'), row.querySelector('[name$="-longitude"]'),
  ];

  if (!window.EA600RouteMap) {
    importButton.disabled = true;
    status.textContent = "The map could not load. You can still enter stop coordinates.";
    return;
  }

  const route = window.EA600RouteMap.create(canvas);
  let track = [];
  let placing = null;
  let returnRow = null;
  let importing = false;

  function isPosition(position) {
    return Array.isArray(position) && position.length === 2
      && Number.isFinite(position[0]) && Math.abs(position[0]) <= 90
      && Number.isFinite(position[1]) && Math.abs(position[1]) <= 180;
  }

  try {
    const value = JSON.parse(trackField.value || "[]");
    if (Array.isArray(value) && value.every((segment) => Array.isArray(segment) && segment.every(isPosition))) {
      track = value;
    }
  } catch {
    // The server renders validation errors next to the original form value.
  }

  function finishPlacement() {
    placing = null;
    cancelButton.hidden = true;
    canvas.classList.remove("geographic-map--placing");
  }

  function updateStops() {
    const stops = [];
    visibleRows().forEach((row, index) => {
      const inputs = coordinateInputs(row);
      const position = inputs.map((input) => input.value === "" ? NaN : Number(input.value));
      const hasPin = isPosition(position);
      row.querySelector("[data-clear-stop]").hidden = inputs.every((input) => input.value === "");
      if (hasPin) {
        const title = row.querySelector('[name$="-title"]').value.trim();
        stops.push({ number: index + 1, title, position });
      }
    });
    if (placing?.hidden) {
      finishPlacement();
      status.textContent = "";
    }
    if (returnRow?.hidden) returnButton.hidden = true;
    route.setStops(stops);
    return stops;
  }

  function updateTrack() {
    route.setTrack(track);
    route.fit(track, updateStops());
    const points = track.reduce((count, segment) => count + segment.length, 0);
    summary.textContent = points ? `GPX track loaded · ${points.toLocaleString()} points` : "";
    clearTrack.hidden = !points;
  }

  async function importTrack() {
    if (!file.files.length) {
      status.textContent = "Choose a GPX file to import.";
      file.focus();
      return;
    }
    const data = new FormData();
    data.append("gpx", file.files[0]);
    data.append("csrfmiddlewaretoken", form.querySelector('[name="csrfmiddlewaretoken"]').value);
    importing = true;
    importButton.disabled = clearTrack.disabled = true;
    status.textContent = "Importing GPX…";
    try {
      const result = await fetch(panel.dataset.importUrl, { method: "POST", body: data });
      if (result.redirected) throw new Error();
      const response = await result.json();
      if (!result.ok) {
        status.textContent = response.error || "The GPX file could not be imported.";
        return;
      }
      track = response.track;
      trackField.value = JSON.stringify(track);
      file.value = "";
      finishPlacement();
      updateTrack();
      status.textContent = "GPX imported. Save the tour to keep the track.";
    } catch {
      status.textContent = "The GPX file could not be imported. Try again.";
    } finally {
      importing = false;
      importButton.disabled = clearTrack.disabled = false;
    }
  }

  importButton.addEventListener("click", importTrack);
  form.addEventListener("submit", (event) => {
    if (importing) {
      event.preventDefault();
      status.textContent = "Wait for the GPX import to finish before continuing.";
      panel.scrollIntoView({ block: "start" });
    }
  });
  clearTrack.addEventListener("click", () => {
    track = [];
    trackField.value = "[]";
    updateTrack();
    status.textContent = "GPX track removed. Save the tour to keep this change.";
  });

  group.addEventListener("builder:rows-changed", updateStops);
  group.addEventListener("change", (event) => {
    if (event.target.matches('[name$="-latitude"], [name$="-longitude"], [name$="-title"]')) updateStops();
  });
  group.addEventListener("click", (event) => {
    const button = event.target.closest("[data-place-stop], [data-clear-stop]");
    if (!button) return;
    const row = button.closest("[data-row]");
    if (button.matches("[data-clear-stop]")) {
      coordinateInputs(row).forEach((input) => { input.value = ""; });
      updateStops();
      row.querySelector("[data-place-stop]").focus();
      return;
    }

    placing = returnRow = row;
    const index = visibleRows().indexOf(row) + 1;
    status.textContent = `Click or tap the map to place stop ${index}.`;
    canvas.classList.add("geographic-map--placing");
    cancelButton.hidden = false;
    returnButton.hidden = true;
    panel.scrollIntoView({ block: "start" });
    canvas.focus({ preventScroll: true });
  });
  route.map.on("click", (event) => {
    if (!placing) return;
    const { lat, lng } = route.map.wrapLatLng(event.latlng);
    const [latitude, longitude] = coordinateInputs(placing);
    latitude.value = lat.toFixed(6);
    longitude.value = lng.toFixed(6);
    const index = visibleRows().indexOf(placing) + 1;
    finishPlacement();
    updateStops();
    status.textContent = `Stop ${index} placed on the map.`;
    returnButton.hidden = false;
  });
  cancelButton.addEventListener("click", () => {
    finishPlacement();
    status.textContent = "Placement cancelled.";
    returnButton.hidden = false;
  });
  returnButton.addEventListener("click", () => {
    if (!returnRow || returnRow.hidden) return;
    returnRow.scrollIntoView({ block: "start" });
    returnRow.querySelector("[data-place-stop]").focus({ preventScroll: true });
  });

  updateTrack();
})();
