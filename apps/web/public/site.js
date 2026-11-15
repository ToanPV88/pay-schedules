// Cải tiến dần cho trang render phía server. Tắt JavaScript thì mọi bảng vẫn đọc được, máy tính
// gửi form GET và server tính; có JavaScript thì máy tính cập nhật tại chỗ và bảng học khu sắp
// xếp không cần tải lại. Câu chữ phải khớp với apps/web/src/views/schedule.ts (calculationText).
(() => {
  const BASIS_NOUNS = {
    annual: "per year",
    monthly: "per month",
    hourly: "per hour",
    daily: "per day",
  };

  function formatCents(cents) {
    const abs = Math.abs(cents);
    const dollars = Math.floor(abs / 100);
    const rest = abs % 100;
    const whole = String(dollars).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
    const fraction = rest === 0 ? "" : `.${String(rest).padStart(2, "0")}`;
    return `${cents < 0 ? "-" : ""}$${whole}${fraction}`;
  }

  function amountOf(row, laneIndex) {
    const cell = row?.querySelectorAll("td")[laneIndex];
    if (!cell || cell.dataset.cents === undefined) {
      return null;
    }
    return Number(cell.dataset.cents);
  }

  // Như stepLabel trong src/format.ts: nhãn chỉ là số thì thêm chữ "Step".
  function stepLabel(row, index) {
    const label = row?.cells[0]?.textContent.trim() ?? "";
    if (label === "") {
      return `Step ${index + 1}`;
    }
    return /^[0-9]+$/.test(label) ? `Step ${label}` : label;
  }

  // Như topText trong src/views/schedule.ts: bậc cuối có số của cột.
  function topText(rows, laneIndex, stepIndex) {
    for (let i = rows.length - 1; i >= 0; i--) {
      const amount = amountOf(rows[i], laneIndex);
      if (amount === null) {
        continue;
      }
      const more = i - stepIndex;
      if (more <= 0) {
        return "This is the top of the lane";
      }
      const steps = more === 1 ? "step" : "steps";
      return `${formatCents(amount)} at ${stepLabel(rows[i], i)} (${more} more ${steps})`;
    }
    return "—";
  }

  function calculate(table, laneIndex, stepIndex) {
    const rows = table.tBodies[0]?.rows ?? [];
    const row = rows[stepIndex];
    const amount = amountOf(row, laneIndex);
    const isTop = stepIndex === rows.length - 1;
    const top = topText(rows, laneIndex, stepIndex);
    if (amount === null) {
      const raise = isTop ? "Top step of this schedule" : "—";
      return {
        amount: "No amount listed for this step and lane",
        perMonth: "—",
        perDay: "—",
        raise,
        top,
      };
    }
    const basis = table.dataset.basis;
    const days = table.dataset.days ? Number(table.dataset.days) : null;
    const text = { amount: `${formatCents(amount)} ${BASIS_NOUNS[basis] ?? ""}`.trim(), top };
    text.perMonth =
      basis === "annual" ? `${formatCents(Math.round(amount / 12))} (12 equal checks)` : "—";
    if (basis === "annual" && days) {
      text.perDay = `${formatCents(Math.round(amount / days))} (${days} contract days)`;
    } else if (basis === "annual") {
      text.perDay = "Not available: the source does not state contract days";
    } else {
      text.perDay = "—";
    }
    if (isTop) {
      text.raise = "Top step of this schedule";
    } else {
      const next = amountOf(rows[stepIndex + 1], laneIndex);
      if (next === null) {
        text.raise = "—";
      } else {
        const diff = next - amount;
        text.raise = `${diff >= 0 ? "+" : ""}${formatCents(diff)} at the next step`;
      }
    }
    return text;
  }

  for (const form of document.querySelectorAll("form[data-calc-table]")) {
    const table = document.getElementById(form.dataset.calcTable);
    const result = document.getElementById(form.dataset.calcResult);
    if (!table || !result) {
      continue;
    }
    const laneSelect = form.elements.namedItem("lane");
    const stepSelect = form.elements.namedItem("step");
    const selection = () => ({
      laneIndex: laneSelect ? Number(laneSelect.value) - 1 : 0,
      stepIndex: stepSelect ? Number(stepSelect.value) - 1 : 0,
    });
    // Ô đang chọn của máy tính được tô trong bảng.
    const markSelected = () => {
      const { laneIndex, stepIndex } = selection();
      for (const cell of table.querySelectorAll("td.is-selected")) {
        cell.classList.remove("is-selected");
      }
      table.tBodies[0]?.rows[stepIndex]
        ?.querySelectorAll("td")
        [laneIndex]?.classList.add("is-selected");
    };
    // Địa chỉ trang giữ lựa chọn (?s=&lane=&step=#calc-…) để gửi link là người nhận thấy đúng số.
    const keepInUrl = () => {
      const url = new URL(window.location.href);
      for (const [key, value] of new FormData(form)) {
        url.searchParams.set(key, String(value));
      }
      url.hash = result.id;
      window.history.replaceState(null, "", url);
    };
    const update = () => {
      const { laneIndex, stepIndex } = selection();
      const text = calculate(table, laneIndex, stepIndex);
      const outputs = {
        amount: text.amount,
        "per-month": text.perMonth,
        "per-day": text.perDay,
        raise: text.raise,
        top: text.top,
      };
      for (const [key, value] of Object.entries(outputs)) {
        const out = result.querySelector(`[data-out="${key}"]`);
        if (out) {
          out.textContent = value;
        }
      }
      markSelected();
    };
    form.addEventListener("change", () => {
      update();
      keepInUrl();
    });
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      update();
      keepInUrl();
    });
    // Bấm một ô có số trong bảng: máy tính chọn đúng lane và bậc của ô đó.
    table.classList.add("is-interactive");
    table.addEventListener("click", (event) => {
      const cell = event.target.closest("td[data-cents]");
      if (!cell || !table.tBodies[0]?.contains(cell)) {
        return;
      }
      const row = cell.parentElement;
      const laneIndex = [...row.querySelectorAll("td")].indexOf(cell);
      if (laneSelect) {
        laneSelect.value = String(laneIndex + 1);
      }
      if (stepSelect) {
        stepSelect.value = String(row.sectionRowIndex + 1);
      }
      update();
      keepInUrl();
    });
    // Mở trang từ link có lựa chọn của bảng này: tô ô đã chọn.
    const own = form.elements.namedItem("s");
    if (own && new URL(window.location.href).searchParams.get("s") === own.value) {
      markSelected();
    }
    // Kết quả đã tự cập nhật khi đổi lựa chọn: nút Calculate chỉ cần khi không có JavaScript.
    const submit = form.querySelector('button[type="submit"]');
    if (submit) {
      submit.hidden = true;
    }
  }

  // Lọc bảng học khu của trang bang theo tên hoặc thành phố (không dấu, không phân biệt hoa thường).
  const fold = (text) =>
    text
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase();
  for (const input of document.querySelectorAll("input[data-filter-table]")) {
    const table = document.getElementById(input.dataset.filterTable);
    const box = input.closest(".table-filter");
    if (!table || !box) {
      continue;
    }
    box.hidden = false;
    const count = box.querySelector("[data-filter-count]");
    const rows = [...table.tBodies[0].rows];
    const texts = rows.map((row) =>
      fold(`${row.cells[0]?.textContent ?? ""} ${row.cells[1]?.textContent ?? ""}`),
    );
    input.addEventListener("input", () => {
      const words = fold(input.value).split(/\s+/).filter(Boolean);
      let shown = 0;
      for (const [i, row] of rows.entries()) {
        const match = words.every((word) => texts[i].includes(word));
        row.hidden = !match;
        shown += Number(match);
      }
      if (count) {
        count.textContent = words.length === 0 ? "" : `${shown} of ${rows.length} districts shown`;
      }
    });
  }

  // Sắp xếp bảng học khu của trang bang khi mọi dòng nằm trên một trang.
  for (const table of document.querySelectorAll('table[data-sortable="true"]')) {
    const headers = [...table.tHead.rows[0].cells];
    const body = table.tBodies[0];
    for (const [index, th] of headers.entries()) {
      const link = th.querySelector("a[data-sort-first]");
      if (!link) {
        continue;
      }
      link.addEventListener("click", (event) => {
        event.preventDefault();
        const current = th.getAttribute("aria-sort");
        let dir = link.dataset.sortFirst;
        if (current) {
          dir = current === "ascending" ? "desc" : "asc";
        }
        const numeric = index > 0;
        const rows = [...body.rows];
        const sortValueOf = (row) => row.cells[index]?.dataset.sortValue ?? "";
        rows.sort((a, b) => {
          const x = sortValueOf(a);
          const y = sortValueOf(b);
          // Dòng thiếu số luôn xếp cuối, dù tăng hay giảm.
          if (x === "" || y === "") {
            return Number(x === "") - Number(y === "");
          }
          const order = numeric ? Number(x) - Number(y) : x.localeCompare(y);
          return dir === "asc" ? order : -order;
        });
        body.append(...rows);
        for (const other of headers) {
          other.removeAttribute("aria-sort");
        }
        th.setAttribute("aria-sort", dir === "asc" ? "ascending" : "descending");
      });
    }
  }

  // Biểu đồ lương theo bậc: đường dóng và chú thích theo bậc gần con trỏ nhất. Biểu đồ vẫn đọc
  // được khi không có JavaScript; số đầy đủ nằm ở bảng ngay phía trên.
  for (const figure of document.querySelectorAll("figure.pay-chart[data-chart]")) {
    let data;
    try {
      data = JSON.parse(figure.dataset.chart);
    } catch {
      continue;
    }
    const svg = figure.querySelector("svg");
    const line = svg?.querySelector(".crosshair");
    const tip = figure.querySelector(".chart-tip");
    if (!svg || !line || !tip || !data.steps?.length) {
      continue;
    }
    const last = data.steps.length - 1;
    const hide = () => {
      line.style.visibility = "hidden";
      tip.hidden = true;
    };
    const show = (event) => {
      const matrix = svg.getScreenCTM();
      if (!matrix) {
        return;
      }
      const point = new DOMPoint(event.clientX, event.clientY).matrixTransform(matrix.inverse());
      const raw = data.dx > 0 ? Math.round((point.x - data.x0) / data.dx) : 0;
      const i = Math.min(last, Math.max(0, raw));
      const x = data.x0 + i * data.dx;
      line.setAttribute("x1", String(x));
      line.setAttribute("x2", String(x));
      line.style.visibility = "visible";
      const title = document.createElement("strong");
      title.textContent = data.steps[i];
      const rows = data.series.map((series, k) => {
        const row = document.createElement("div");
        const key = document.createElement("span");
        key.className = `key s${k + 1}`;
        const name = document.createElement("span");
        name.textContent = series.label;
        const value = document.createElement("span");
        const cents = series.cents[i];
        value.textContent = cents === null || cents === undefined ? "—" : formatCents(cents);
        row.append(key, name, value);
        return row;
      });
      tip.replaceChildren(title, ...rows);
      tip.hidden = false;
      // Vị trí theo phần trăm chiều rộng SVG, giữ chú thích trong khung biểu đồ.
      const box = svg.getBoundingClientRect();
      const frame = figure.getBoundingClientRect();
      const left = box.left - frame.left + (x / data.w) * box.width;
      const half = tip.offsetWidth / 2;
      const clamped = Math.min(frame.width - half - 4, Math.max(half + 4, left));
      tip.style.left = `${clamped}px`;
    };
    svg.addEventListener("pointermove", show);
    svg.addEventListener("pointerdown", show);
    svg.addEventListener("pointerleave", hide);
  }

  // Cỡ chữ của bảng lương: bốn mức, nhớ trong trình duyệt (bỏ qua nếu bộ nhớ bị chặn).
  const TABLE_SIZES = [0.85, 1, 1.15, 1.3];
  const textTools = document.querySelectorAll("[data-text-size]");
  if (textTools.length > 0) {
    let level = 1;
    try {
      const saved = localStorage.getItem("ps-table-size");
      if (saved !== null && TABLE_SIZES[Number(saved)] !== undefined) {
        level = Number(saved);
      }
    } catch {
      // Bộ nhớ trình duyệt bị chặn: dùng cỡ mặc định.
    }
    const apply = () => {
      document.documentElement.style.setProperty("--table-scale", String(TABLE_SIZES[level]));
      for (const box of textTools) {
        box.querySelector('[data-size="-1"]').disabled = level === 0;
        box.querySelector('[data-size="1"]').disabled = level === TABLE_SIZES.length - 1;
      }
    };
    for (const box of textTools) {
      box.hidden = false;
      box.addEventListener("click", (event) => {
        const button = event.target.closest("button[data-size]");
        if (!button) {
          return;
        }
        level = Math.min(TABLE_SIZES.length - 1, Math.max(0, level + Number(button.dataset.size)));
        try {
          localStorage.setItem("ps-table-size", String(level));
        } catch {
          // Không lưu được thì vẫn đổi cỡ cho trang này.
        }
        apply();
      });
    }
    apply();
  }

  // Gợi ý học khu khi gõ (combobox theo mẫu ARIA). Không có JavaScript thì form gửi /search như cũ.
  for (const input of document.querySelectorAll("input[data-suggest]")) {
    const row = input.closest(".search-row");
    if (!row) {
      continue;
    }
    const list = document.createElement("ul");
    list.id = `${input.id}-suggest`;
    list.className = "suggest";
    list.setAttribute("role", "listbox");
    list.hidden = true;
    row.append(list);
    input.setAttribute("role", "combobox");
    input.setAttribute("aria-autocomplete", "list");
    input.setAttribute("aria-expanded", "false");
    input.setAttribute("aria-controls", list.id);

    // Ô của /calculator và /compare dẫn vào luồng của chính trang đó ("{key}" = bang/học khu).
    const targetOf = (hit) =>
      input.dataset.suggestHref ? input.dataset.suggestHref.replace("{key}", hit.key) : hit.href;
    let items = [];
    let active = -1;
    let timer = 0;
    let controller = null;

    const close = () => {
      list.hidden = true;
      input.setAttribute("aria-expanded", "false");
      input.removeAttribute("aria-activedescendant");
      active = -1;
    };
    const highlight = (index) => {
      active = index;
      for (const [i, li] of [...list.children].entries()) {
        li.setAttribute("aria-selected", String(i === index));
      }
      if (index >= 0) {
        input.setAttribute("aria-activedescendant", `${list.id}-${index}`);
        list.children[index]?.scrollIntoView({ block: "nearest" });
      } else {
        input.removeAttribute("aria-activedescendant");
      }
    };
    const render = (hits) => {
      items = hits;
      list.replaceChildren();
      for (const [i, hit] of hits.entries()) {
        const li = document.createElement("li");
        li.id = `${list.id}-${i}`;
        li.setAttribute("role", "option");
        li.setAttribute("aria-selected", "false");
        const name = document.createElement("span");
        name.className = "suggest-name";
        name.textContent = hit.name;
        const place = document.createElement("span");
        place.className = "suggest-place";
        place.textContent = hit.hasSchedule ? hit.place : `${hit.place} · No schedule yet`;
        li.append(name, place);
        // mousedown thay cho click để chọn trước khi ô nhập mất tiêu điểm và danh sách đóng.
        li.addEventListener("mousedown", (event) => {
          event.preventDefault();
          window.location.href = targetOf(hit);
        });
        li.addEventListener("mousemove", () => highlight(i));
        list.append(li);
      }
      if (hits.length === 0) {
        close();
        return;
      }
      list.hidden = false;
      input.setAttribute("aria-expanded", "true");
      highlight(-1);
    };
    const fetchHits = async () => {
      const query = input.value.trim();
      if (query.length < 2) {
        render([]);
        return;
      }
      controller?.abort();
      controller = new AbortController();
      try {
        const url = `${input.dataset.suggest}?q=${encodeURIComponent(query)}`;
        const res = await fetch(url, { signal: controller.signal });
        if (!res.ok) {
          return;
        }
        const data = await res.json();
        if (data.q === input.value.trim().slice(0, 80)) {
          render(data.hits ?? []);
        }
      } catch {
        // Bị hủy vì người dùng gõ tiếp, hoặc lỗi mạng: giữ nguyên form tìm kiếm thường.
      }
    };
    input.addEventListener("input", () => {
      clearTimeout(timer);
      timer = setTimeout(fetchHits, 150);
    });
    input.addEventListener("keydown", (event) => {
      if (list.hidden || items.length === 0) {
        return;
      }
      if (event.key === "ArrowDown") {
        event.preventDefault();
        highlight((active + 1) % items.length);
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        highlight(active <= 0 ? items.length - 1 : active - 1);
      } else if (event.key === "Enter" && active >= 0) {
        event.preventDefault();
        window.location.href = targetOf(items[active]);
      } else if (event.key === "Escape") {
        close();
      }
    });
    input.addEventListener("blur", () => setTimeout(close, 100));
  }

  // Rê chuột hoặc chạm vào ô của bảng lương: tô cả hàng và cột để dò bảng lớn (vd. 24 lane × 30 bậc).
  for (const table of document.querySelectorAll("table.schedule")) {
    let marked = [];
    const clear = () => {
      for (const el of marked) {
        el.classList.remove("hl-row", "hl-col", "hl-cell");
      }
      marked = [];
    };
    table.addEventListener("pointerover", (event) => {
      const cell = event.target.closest("td, th");
      if (!cell || !table.tBodies[0]?.contains(cell)) {
        return;
      }
      clear();
      const row = cell.parentElement;
      row.classList.add("hl-row");
      marked.push(row);
      const col = cell.cellIndex;
      if (col > 0) {
        for (const r of table.rows) {
          const c = r.cells[col];
          if (c) {
            c.classList.add("hl-col");
            marked.push(c);
          }
        }
        cell.classList.add("hl-cell");
      }
    });
    table.addEventListener("pointerleave", clear);
  }
})();
