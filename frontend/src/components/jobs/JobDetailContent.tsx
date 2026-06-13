"use client";

import { MapPin, Building2 } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Job } from "@/types/job";
import { PlatformBadge } from "./PlatformBadge";
import { Separator } from "@/components/ui/separator";

/** Known Spanish section-header keywords (no colon needed). */
const STANDALONE_HEADERS = [
  "Quiénes somos",
  "Sobre nosotros",
  "Te ofrecemos",
  "Tus funciones",
  "El reto",
  "Jornada",
  "Horario",
  "Contrato",
  "Salario",
  "Beneficios",
  "Requisitos",
  "Será un plus si",
  "Será un plus",
  "Qué se ofrece",
  "Se ofrece",
  "Igualdad de oportunidades",
];

/** Headers that always end with `:` or `?` — matched as a unit. */
const HEADER_WITH_PUNCTUATION = new RegExp(
  "^(¿[^?\\n]+?\\?" +
    "|(?:Mis[íi]ón" +
    "|Funciones?[^:\\n]*" +
    "|Requisitos[^:\\n]*" +
    "|Perfil[^:\\n]*" +
    "|Ofrecemos[^:\\n]*" +
    "|Se requiere[^:\\n]*" +
    "|Se ofrece[^:\\n]*" +
    "|Buscamos[^:\\n]*" +
    "|Valoraremos[^:\\n]*" +
    "|Descripción[^:\\n]*)" +
    ")[:?]",
  "im",
);

/**
 * Spanish words that typically introduce a new job-description item (be it a
 * responsibility, a requirement, or a benefit).  These are the words we look
 * for to split a run-on paragraph into a list.
 *
 * Only words IN THIS LIST trigger a split.  There is NO general fallback
 * that matches any capitalized word (that produced too many false positives
 * like "Recursos Humanos" and "Punto de Venta" being split).
 */
const ITEM_STARTERS =
  // infinitive verbs (common for "Tus funciones" sections)
  "(?:Recibir|Gestionar|Garantizar|Apoyar|Coordinar|Supervisar|" +
  "Realizar|Proponer|Atender|Dar|Preparar|Elaborar|Participar|" +
  "Controlar|Evaluar|Mantener|Desarrollar|Implementar|Asegurar|" +
  "Verificar|Validar|Monitorear|Liderar|Dirigir|Planificar|" +
  "Organizar|Tramitar|Resolver|Asistir|Colaborar|Presentar|" +
  "Capacitar|Formar|Seleccionar|Redactar|Crear|Dis[eé]ñar|" +
  "Incorporarse|Tener|Estar|Haber|Fomentar|Promover|Impulsar|" +
  "Negociar|Reportar|Archivar|Registrar|Actualizar|Informar|" +
  // requirement / benefit nouns (only unambiguous ones)
  "Experiencia|Persona|Manejo|Oficina|Jornada|Horario|" +
  "Tarjeta|Incorporación|Graduado|Valorable|" +
  "Disponibilidad|Buscamos|Ofrecemos|Valoramos|Valoraremos|" +
  "Flexibilidad|Remoto|Presencial|" +
  // common verbs / auxiliaries that start items
  "Será|Tienes|Te[\\s\\n]|Que[\\s\\n]|Nos|Nuestra|Formarás|" +
  "Ubicaci[oó]n|Ingl[eé]s|Franc[eé]s|Alemán" +
  ")";

/**
 * Section header phrases that may end up as list items after splitting.
 * These are promoted back to bold headings.
 */
const LIST_TO_HEADER: [string, string][] = [
  ["Requisitos", "**Requisitos**"],
  ["Será un plus", "**Será un plus**"],
  ["Qu[ée] se ofrece", "**Qué se ofrece**"],
  ["Se ofrece", "**Se ofrece**"],
  ["Igualdad de oportunidades", "**Igualdad de oportunidades**"],
];

/**
 * Preprocess plain-text job descriptions into readable markdown.
 *
 * Scraped descriptions are one continuous blob. This:
 *  1. Inserts paragraph breaks at sentence boundaries
 *  2. Detects known section headers even mid-paragraph and promotes them to
 *     their own line (so step 4 can bold them)
 *  3. Bolds section headers ending with `?` or `:`
 *  4. Bolds standalone section headers (now at line-start after step 2)
 *  5. Puts bolded headers on their own line (e.g. `**Header**text`)
 *  6. Converts contiguous verb/noun-led items into markdown list items
 *  7. Promotes known section keywords from list items back to bold headers
 *  8. Converts enumerated lines ("1. foo") into list items
 */
function enrich(text: string): string {
  let result = text;

  // ── 1. PARAGRAPH BREAKS (sentence boundaries) ────────────────────────
  if (!result.includes("\n\n")) {
    result = result.replace(/([.!?])\s+(?=[A-Z¿¡])/g, "$1\n\n");
  }

  // ── 2. MID-PARAGRAPH HEADER DETECTION ────────────────────────────────
  // Some section headers (e.g. "Requisitos", "Será un plus") appear
  // mid-line because the text before them has no period.  Add a paragraph
  // break before them so step 4 can bold them.
  // NOTE: "Se ofrece" is intentionally absent — it always appears after
  // a period (already at line-start) and would conflict with "Qué se ofrece".
  {
    const midHeaders: [string, boolean][] = [
      ["Requisitos", true],
      ["Será un plus", true],
      ["Qu[ée] se ofrece", true],
      ["Igualdad de oportunidades", false],
    ];
    for (const [h, caseInsensitive] of midHeaders) {
      // Only match when preceded by a non-whitespace char (mid-line, not
      // at line-start).  Case-insensitive only for reliable keywords.
      const re = new RegExp(
        `(?<=\\S)\\s+(?=${h}(?=[\\s:;?.!,]))`,
        caseInsensitive ? "gi" : "g",
      );
      result = result.replace(re, "\n\n");
    }
  }

  // ── 3. BOLD HEADERS (with colon / question mark) ─────────────────────
  result = result.replace(HEADER_WITH_PUNCTUATION, "**$1**");

  // ── 4. BOLD STANDALONE HEADERS ───────────────────────────────────────
  for (const phrase of STANDALONE_HEADERS) {
    const re = new RegExp(
      `(^|\\n\\n)(${phrase})(?=[\\s:;?.!])`,
      "gim",
    );
    result = result.replace(re, "$1**$2**");
  }

  // ── 5. BOLD HEADER ON ITS OWN LINE ───────────────────────────────────
  // If `**Header**` has content on the same line (space + text), insert a
  // line break and consume the trailing space so the next line is clean.
  result = result.replace(/\*\*(.+?)\*\*[ \t]+(?=\S)/g, "**$1**\n\n");

  // ── 6. LIST-LIKE ITEMS ───────────────────────────────────────────────
  // Detect sequences of capitalized item-starters mid-paragraph  ->
  // convert to markdown list items.  Only matches when preceded by a
  // lowercase letter (so it operates within a sentence, not after a period).
  result = result.replace(
    new RegExp("(?<=[a-zñáéíóú])\\s+(?=" + ITEM_STARTERS + ")", "g"),
    "\n- ",
  );

  // ── 7. PROMOTE SECTION KEYWORDS FROM LIST ITEMS TO BOLD HEADERS ──────
  // After splitting, some section headers end up as `- Requisitos`.  Fix that.
  for (const [pattern, replacement] of LIST_TO_HEADER) {
    const re = new RegExp(`^- (${pattern})(?=\\s|$)`, "gim");
    result = result.replace(re, `${replacement}\n`);
  }

  // ── 8. ENUMERATED LINES ──────────────────────────────────────────────
  result = result.replace(/^(\d+)\.\s+/gm, "- ");

  return result;
}

interface JobDetailContentProps {
  job: Job;
}

export function JobDetailContent({ job }: JobDetailContentProps) {
  return (
    <div className="space-y-6">
      {/* Title + badges */}
      <div>
        <div className="mb-2 flex flex-wrap gap-2">
          {job.source && <PlatformBadge platform={job.source} />}
        </div>
        <h1 className="font-display text-2xl font-bold tracking-tight">
          {job.title}
        </h1>
      </div>

      {/* Company + Location */}
      <div className="flex flex-wrap items-center gap-4 text-sm text-muted-foreground">
        <span className="inline-flex items-center gap-1.5">
          <Building2 className="h-4 w-4" />
          {job.company}
        </span>
        {job.location && (
          <span className="inline-flex items-center gap-1.5">
            <MapPin className="h-4 w-4" />
            {job.location}
          </span>
        )}
      </div>

      <Separator />

      {/* Description with Markdown */}
      {job.description && (
        <div>
          <h3 className="mb-2 font-display text-sm font-semibold text-muted-foreground">
            Description
          </h3>
          <div className="markdown-prose">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {enrich(job.description)}
            </ReactMarkdown>
          </div>
        </div>
      )}
    </div>
  );
}
