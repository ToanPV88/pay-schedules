/**
 * "Questions people ask" của trang học khu: câu hỏi sinh từ chính dữ liệu của trang, kèm dữ liệu có
 * cấu trúc (FAQPage, BreadcrumbList) cho máy tìm kiếm. Câu trả lời chỉ nêu số có trong bảng.
 */
import type { District, Schedule, Summary } from "@pay-schedules/db";
import { html, raw } from "hono/html";
import {
  formatCents,
  formatDate,
  hostOf,
  payBasisNoun,
  safeHttpUrl,
  schoolYearLabel,
  sourceLanding,
} from "../format";
import type { Html } from "./layout";
import { districtPath } from "./parts";

export interface FaqData {
  district: District;
  year: string;
  schedules: Schedule[];
  /** Mốc so sánh của năm đang hiện (BA bậc 1...), null khi pipeline chưa tính hoặc khác năm. */
  summary: Summary | null;
  minCents: number | null;
  maxCents: number | null;
  basis: Schedule["payBasis"] | null;
}

export interface Faq {
  question: string;
  answer: string;
}

function plural(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`;
}

export function districtFaqs(data: FaqData): Faq[] {
  const { district, schedules } = data;
  const first = schedules[0];
  if (!first) {
    return [];
  }
  const name = district.name;
  const year = schoolYearLabel(data.year);
  const noun = data.basis ? ` ${payBasisNoun(data.basis)}` : "";
  const faqs: Faq[] = [];

  const start = data.summary?.schoolYear === data.year ? data.summary.startBaCents : null;
  if (start !== null && data.basis === "annual") {
    faqs.push({
      question: `What is the starting teacher salary in ${name}?`,
      answer: `Under the ${year} salary schedule, a teacher with a bachelor’s degree on the first step earns ${formatCents(start)} per year. Credited experience and graduate credits place a teacher on a higher step or lane.`,
    });
  } else if (data.minCents !== null) {
    faqs.push({
      question: `What is the lowest teacher salary in ${name}?`,
      answer: `The lowest amount on the ${year} teacher salary schedule is ${formatCents(data.minCents)}${noun}.`,
    });
  }
  if (data.maxCents !== null) {
    faqs.push({
      question: `What is the highest teacher salary in ${name}?`,
      answer: `The highest amount on the ${year} teacher salary schedule is ${formatCents(data.maxCents)}${noun}, at the top step of the highest lane. Stipends and extra-duty pay are not included.`,
    });
  }

  const lanes = first.lanes.length;
  const steps = first.steps.length;
  const shape =
    lanes > 0
      ? `${plural(steps, "step", "steps")} (rows, usually years of experience) and ${plural(lanes, "lane", "lanes")} (columns, usually education level)`
      : `${plural(steps, "step", "steps")} and a single salary column`;
  const others =
    schedules.length > 1
      ? ` The district publishes ${schedules.length} teacher schedules for ${year}; the first one is described here.`
      : "";
  faqs.push({
    question: `How does the ${name} teacher salary schedule work?`,
    answer: `The ${year} schedule has ${shape}. A teacher’s salary is the amount where their step and lane meet.${others}`,
  });

  if (first.contractDays !== null) {
    faqs.push({
      question: `How many days are in the ${name} teacher contract?`,
      answer: `The ${year} schedule is based on ${first.contractDays} contract days.`,
    });
  }

  const landing = sourceLanding(first.source.url);
  const url = safeHttpUrl(first.source.url);
  const where = landing
    ? landing.label
    : url
      ? `a document on ${hostOf(url)}`
      : "a public document";
  const page = first.source.page !== null ? `, page ${first.source.page}` : "";
  faqs.push({
    question: "Where do these figures come from?",
    answer: `From ${where}${page}, retrieved ${formatDate(first.source.fetchedAt)}. The table is extracted automatically and checked for consistency; the district’s own document governs if they differ.`,
  });
  return faqs;
}

/** Chuỗi JSON an toàn để đặt trong thẻ <script>: không thể đóng thẻ hay mở chú thích HTML. */
export function jsonForScript(value: unknown): string {
  return JSON.stringify(value)
    .replaceAll("<", "\\u003c")
    .replaceAll(">", "\\u003e")
    .replaceAll("&", "\\u0026")
    .replaceAll(" ", "\\u2028")
    .replaceAll(" ", "\\u2029");
}

/** `extra`: các nút JSON-LD khác của trang (vd. Dataset), gộp vào cùng một @graph. */
export function faqSection(origin: string, data: FaqData, extra: object[] = []): Html {
  const faqs = districtFaqs(data);
  if (faqs.length === 0) {
    return html``;
  }
  // Câu hỏi thu gọn được (<details>): câu đầu mở sẵn, nội dung vẫn nằm trong HTML cho máy tìm kiếm.
  const items = faqs.map(
    (
      f,
      i,
    ) => html`<details class="faq"${i === 0 ? raw(" open") : ""}><summary><h3>${f.question}</h3></summary><p>${f.answer}</p></details>
`,
  );
  const { district } = data;
  const graph = [
    {
      "@type": "FAQPage",
      mainEntity: faqs.map((f) => ({
        "@type": "Question",
        name: f.question,
        acceptedAnswer: { "@type": "Answer", text: f.answer },
      })),
    },
    {
      "@type": "BreadcrumbList",
      itemListElement: [
        { "@type": "ListItem", position: 1, name: "Home", item: `${origin}/` },
        {
          "@type": "ListItem",
          position: 2,
          name: district.state.name,
          item: `${origin}/${district.state.slug}`,
        },
        {
          "@type": "ListItem",
          position: 3,
          name: district.name,
          item: `${origin}${districtPath(district.state.slug, district.slug)}`,
        },
      ],
    },
  ];
  const ld = jsonForScript({ "@context": "https://schema.org", "@graph": [...graph, ...extra] });
  return html`<section aria-labelledby="faq-heading">
<h2 id="faq-heading">Questions people ask</h2>
${items}</section>
<script type="application/ld+json">${raw(ld)}</script>`;
}
