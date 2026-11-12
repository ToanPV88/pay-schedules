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

  function calculate(table, laneIndex, stepIndex) {
    const rows = table.tBodies[0]?.rows ?? [];
    const row = rows[stepIndex];
    const amount = amountOf(row, laneIndex);
    const isTop = stepIndex === rows.length - 1;
    if (amount === null) {
      const raise = isTop ? "Top step of this schedule" : "—";
      return { amount: "No amount listed for this step and lane", perDay: "—", raise };
    }
    const basis = table.dataset.basis;
    const days = table.dataset.days ? Number(table.dataset.days) : null;
    const text = { amount: `${formatCents(amount)} ${BASIS_NOUNS[basis] ?? ""}`.trim() };
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
    const update = () => {
      const lane = form.elements.namedItem("lane");
      const step = form.elements.namedItem("step");
      const laneIndex = lane ? Number(lane.value) - 1 : 0;
      const stepIndex = step ? Number(step.value) - 1 : 0;
      const text = calculate(table, laneIndex, stepIndex);
      result.querySelector('[data-out="amount"]').textContent = text.amount;
      result.querySelector('[data-out="per-day"]').textContent = text.perDay;
      result.querySelector('[data-out="raise"]').textContent = text.raise;
    };
    form.addEventListener("change", update);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      update();
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
})();
