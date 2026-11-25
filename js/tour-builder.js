function bindRows(group) {
  const list = group.querySelector("[data-editor-rows]");
  const prefix = group.dataset.editorGroup;
  const total = group.querySelector(`[name="${prefix}-TOTAL_FORMS"]`);
  const template = group.querySelector("[data-empty-form]");
  const empty = group.querySelector("[data-empty-rows]");
  const isStops = prefix === "stops";
  const visibleRows = () => [...list.children].filter((row) => !row.hidden);
  const orderInput = (row) => row.querySelector(isStops ? '[name$="-ORDER"]' : '[name$="-number"]');

  function refresh() {
    const rows = visibleRows();
    empty.hidden = rows.length > 0;
    rows.forEach((row, index) => {
      const field = orderInput(row);
      if (isStops) field.value = index + 1;
      row.querySelector("[data-row-order]").textContent = isStops ? `Stop ${index + 1}` : `Day ${field.value || "—"}`;
      row.querySelector('[data-move="-1"]').disabled = index === 0;
      row.querySelector('[data-move="1"]').disabled = index === rows.length - 1;
    });
    group.dispatchEvent(new Event("builder:rows-changed"));
  }

  const sortByOrder = () => {
    visibleRows()
      .sort((first, second) => (Number(orderInput(first).value) || Infinity) - (Number(orderInput(second).value) || Infinity))
      .forEach((row) => list.appendChild(row));
    refresh();
  };

  group.querySelector("[data-add-row]").addEventListener("click", () => {
    const index = Number(total.value);
    const fragment = template.content.cloneNode(true);
    fragment.querySelectorAll("*").forEach((element) => {
      for (const attribute of element.attributes) {
        if (attribute.value.includes("__prefix__")) {
          attribute.value = attribute.value.replaceAll("__prefix__", index);
        }
      }
    });
    const row = fragment.querySelector("[data-row]");
    if (!isStops) {
      const numbers = new Set(visibleRows().map((existing) => Number(orderInput(existing).value)));
      let next = Math.max(0, ...numbers) + 1;
      if (next > 32767) {
        next = 1;
        while (numbers.has(next)) next += 1;
      }
      orderInput(row).value = next;
    }
    list.appendChild(fragment);
    total.value = index + 1;
    row.querySelector("details").open = true;
    refresh();
    row.querySelector('[name$="-title"]').focus();
  });

  group.addEventListener("click", (event) => {
    const button = event.target.closest("[data-move], [data-remove-row]");
    if (!button) return;
    const row = button.closest("[data-row]");
    if (button.hasAttribute("data-remove-row")) {
      row.querySelector('[name$="-DELETE"]').checked = true;
      row.hidden = true;
      group.querySelector("[data-add-row]").focus();
    } else {
      const rows = visibleRows();
      const direction = Number(button.dataset.move);
      const neighbour = rows[rows.indexOf(row) + direction];
      if (!neighbour) return;
      if (!isStops) {
        const movedNumber = orderInput(row);
        const otherNumber = orderInput(neighbour);
        [movedNumber.value, otherNumber.value] = [otherNumber.value, movedNumber.value];
      }
      if (direction < 0) neighbour.before(row);
      else neighbour.after(row);
    }
    refresh();
    if (!row.hidden && button.disabled) row.querySelector("summary").focus();
  });

  group.addEventListener("input", (event) => {
    if (event.target.matches('[name$="-title"]')) {
      const row = event.target.closest("[data-row]");
      row.querySelector("[data-row-title]").textContent = event.target.value.trim() || (isStops ? "New stop" : "New day");
    }
  });
  group.addEventListener("change", (event) => {
    if (!isStops && event.target.matches('[name$="-number"]')) sortByOrder();
  });

  sortByOrder();
}

function bindSlug(form) {
  const title = form.querySelector("#id_title");
  const slug = form.querySelector("#id_slug");
  let automatic = !slug.value;
  slug.addEventListener("input", () => { automatic = !slug.value; });
  title.addEventListener("input", () => {
    if (automatic) {
      slug.value = title.value.normalize("NFKD").toLowerCase()
        .replace(/[\u0300-\u036f]/g, "")
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-|-$/g, "")
        .slice(0, 160);
    }
  });
}

function createPhotoImage(photo) {
  const image = document.createElement("img");
  image.src = photo.url;
  image.alt = "";
  image.loading = "lazy";
  return image;
}

function bindPhotoLibrary(dialog) {
  const grid = dialog.querySelector("[data-library-photos]");
  const search = dialog.querySelector("[data-photo-search]");
  const status = dialog.querySelector("[data-photo-status]");
  const pager = dialog.querySelector("[data-photo-pages]");
  const previous = dialog.querySelector("[data-photo-back]");
  const next = dialog.querySelector("[data-photo-next]");
  const upload = dialog.querySelector("[data-photo-upload]");
  let picker = null;
  let currentPage = 1;
  let request;
  let searchTimer;

  const setStatus = (node, text) => {
    node.textContent = text;
    node.hidden = !text;
  };

  function picked(photo) {
    return picker?.querySelector(`[data-photo-id="${photo.id}"]`);
  }

  function selectPhoto(photo) {
    if (!picker) return;
    const multiple = picker.hasAttribute("data-multiple");
    const selected = picker.querySelector("[data-picked-photos]");
    const existing = picked(photo);
    if (multiple && existing) {
      existing.remove();
      return;
    }
    if (!multiple) selected.replaceChildren();

    const item = document.createElement("div");
    item.className = "builder-picked-photo";
    item.dataset.photoId = photo.id;
    const input = document.createElement("input");
    input.type = "hidden";
    input.name = picker.dataset.field;
    input.value = photo.id;
    const title = document.createElement("span");
    title.textContent = photo.title;
    const remove = document.createElement("button");
    remove.type = "button";
    remove.dataset.removePhoto = "";
    remove.setAttribute("aria-label", `Remove ${photo.title}`);
    remove.textContent = "×";
    item.append(input, createPhotoImage(photo), title, remove);
    selected.appendChild(item);

    if (!multiple) dialog.close();
  }

  async function loadPhotos(page = 1) {
    request?.abort();
    request = new AbortController();
    const params = new URLSearchParams({ q: search.value, page: String(page) });
    pager.hidden = true;
    grid.replaceChildren();
    setStatus(status, "Loading photos…");
    try {
      const response = await fetch(`${dialog.dataset.photoUrl}?${params}`, { signal: request.signal });
      if (!response.ok || response.redirected) throw new Error("Photo library unavailable");
      const data = await response.json();
      currentPage = data.page;
      setStatus(status, data.photos.length ? "" : "No photos found.");
      for (const photo of data.photos) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "builder-library-photo";
        button.setAttribute("aria-pressed", String(Boolean(picked(photo))));
        const title = document.createElement("span");
        title.textContent = photo.title;
        button.append(createPhotoImage(photo), title);
        button.addEventListener("click", () => {
          selectPhoto(photo);
          button.setAttribute("aria-pressed", String(Boolean(picked(photo))));
        });
        grid.appendChild(button);
      }
      previous.disabled = !data.has_previous;
      next.disabled = !data.has_next;
      pager.hidden = !data.has_previous && !data.has_next;
    } catch (error) {
      if (error.name !== "AbortError") setStatus(status, "Could not load photos. Open the library again to retry.");
    }
  }

  document.addEventListener("click", (event) => {
    const trigger = event.target.closest("[data-choose-photos]");
    if (trigger) {
      picker = trigger.closest("[data-photo-picker]");
      search.value = "";
      dialog.showModal();
      loadPhotos();
      search.focus();
    }
    const remove = event.target.closest("[data-remove-photo]");
    if (remove) {
      const target = remove.closest("[data-photo-picker]");
      remove.closest("[data-photo-id]").remove();
      target.querySelector("[data-choose-photos]").focus();
    }
  });

  search.addEventListener("input", () => {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(() => loadPhotos(), 250);
  });
  previous.addEventListener("click", () => loadPhotos(currentPage - 1));
  next.addEventListener("click", () => loadPhotos(currentPage + 1));
  dialog.addEventListener("close", () => {
    request?.abort();
    window.clearTimeout(searchTimer);
    picker = null;
  });

  upload?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const current = picker;
    const submit = upload.querySelector('button[type="submit"]');
    const message = upload.querySelector("[data-upload-status]");
    submit.disabled = true;
    setStatus(message, "Uploading…");
    try {
      const response = await fetch(upload.action, { method: "POST", body: new FormData(upload) });
      if (response.redirected) throw new Error("Session expired");
      const data = await response.json();
      if (!response.ok) {
        const errors = Object.values(data.errors || {}).flat().map((error) => error.message);
        setStatus(message, errors.join(" ") || "The photo could not be uploaded.");
        return;
      }
      upload.reset();
      if (current && current === picker) selectPhoto(data.photo);
      setStatus(message, "Photo saved to the library.");
      if (dialog.open) loadPhotos();
    } catch {
      setStatus(message, "The photo could not be uploaded. Try again.");
    } finally {
      submit.disabled = false;
    }
  });
}

const editor = document.querySelector("[data-builder-form]");
if (editor) {
  editor.querySelectorAll("[data-editor-group]").forEach(bindRows);
  bindSlug(editor);
  bindPhotoLibrary(document.querySelector("[data-photo-dialog]"));
}
