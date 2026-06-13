// Build copy/download text (Markdown / HTML) from the Table tab's display model,
// plus pretty JSON from the raw document. All driven by the same DisplayModel the
// on-screen table uses, so exports always match what's shown.

import type { DisplayModel, DisplaySection } from "./tableModel";
import type { TableDocData } from "./types";

function headerCols(m: DisplayModel, sec: DisplaySection): string[] {
  return [
    "Name",
    ...(m.showCoords ? ["Lat,Lon"] : []),
    "Dist.",
    "GL",
    "ETA",
    ...(sec.showRoad ? ["Road"] : []),
    "Notes",
  ];
}

function rowCells(m: DisplayModel, sec: DisplaySection, i: number): string[] {
  const r = sec.rows[i];
  return [
    r.name,
    ...(m.showCoords ? [r.latlon ?? ""] : []),
    r.dist,
    r.marker,
    r.eta,
    ...(sec.showRoad ? [r.road] : []),
    r.notes,
  ];
}

function sectionMeta(sec: DisplaySection): string {
  const parts = [
    sec.departure ? `Departs ${sec.departure}` : null,
    sec.distance,
    sec.speed,
  ].filter(Boolean);
  return parts.join(" · ");
}

export function buildMarkdown(m: DisplayModel): string {
  const out: string[] = [];
  for (const sec of m.sections) {
    out.push(`## ${sec.title}`);
    out.push(`_${sectionMeta(sec)}_`);
    if (sec.sun) out.push(`_☀ sunrise ${sec.sun.sunrise} · sunset ${sec.sun.sunset}_`);
    out.push("");
    const cols = headerCols(m, sec);
    out.push(`| ${cols.join(" | ")} |`);
    out.push(`| ${cols.map(() => "---").join(" | ")} |`);
    for (let i = 0; i < sec.rows.length; i++) {
      out.push(`| ${rowCells(m, sec, i).join(" | ")} |`);
    }
    if (sec.cue.length) {
      const etaOn = sec.cue.some((c) => c.eta);
      out.push("");
      out.push("### Turn-by-turn");
      const cc = ["Mile", ...(etaOn ? ["ETA"] : []), "Cue"];
      out.push(`| ${cc.join(" | ")} |`);
      out.push(`| ${cc.map(() => "---").join(" | ")} |`);
      for (const c of sec.cue) {
        const cells = [c.mile, ...(etaOn ? [c.eta] : []), c.cue];
        out.push(`| ${cells.join(" | ")} |`);
      }
    }
    out.push("");
  }
  return out.join("\n").trimEnd() + "\n";
}

function esc(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

export function buildHtml(m: DisplayModel): string {
  const body: string[] = [];
  for (const sec of m.sections) {
    body.push(`<h2>${esc(sec.title)}</h2>`);
    const meta = [sectionMeta(sec), sec.sun ? `☀ sunrise ${sec.sun.sunrise} · sunset ${sec.sun.sunset}` : null]
      .filter(Boolean)
      .join(" — ");
    if (meta) body.push(`<p class="meta">${esc(meta)}</p>`);
    const cols = headerCols(m, sec);
    body.push('<table class="gpxtable">');
    body.push(`<thead><tr>${cols.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead>`);
    body.push("<tbody>");
    for (let i = 0; i < sec.rows.length; i++) {
      body.push(`<tr>${rowCells(m, sec, i).map((c) => `<td>${esc(c)}</td>`).join("")}</tr>`);
    }
    body.push("</tbody></table>");
    if (sec.cue.length) {
      const etaOn = sec.cue.some((c) => c.eta);
      const cc = ["Mile", ...(etaOn ? ["ETA"] : []), "Cue"];
      body.push("<h3>Turn-by-turn</h3>");
      body.push('<table class="gpxtable">');
      body.push(`<thead><tr>${cc.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead>`);
      body.push("<tbody>");
      for (const c of sec.cue) {
        const cells = [c.mile, ...(etaOn ? [c.eta] : []), c.cue];
        body.push(`<tr>${cells.map((x) => `<td>${esc(x)}</td>`).join("")}</tr>`);
      }
      body.push("</tbody></table>");
    }
  }
  const css =
    "body{font-family:system-ui,sans-serif;color:#1e293b;max-width:64rem;margin:2rem auto;padding:0 1rem}" +
    "table.gpxtable{width:100%;border-collapse:collapse;margin-bottom:1.5rem}" +
    "th{text-align:left;font-size:.75rem;text-transform:uppercase;letter-spacing:.05em;color:#64748b;border-bottom:1px solid #e2e8f0;padding:.5rem}" +
    "td{border-bottom:1px solid #f1f5f9;padding:.35rem .5rem}" +
    ".meta{color:#64748b;font-size:.875rem}";
  return `<!doctype html>\n<html><head><meta charset="utf-8"><title>${esc(m.name)}</title><style>${css}</style></head>\n<body>\n${body.join("\n")}\n</body></html>\n`;
}

export function buildJson(doc: TableDocData): string {
  return JSON.stringify(doc, null, 2);
}
