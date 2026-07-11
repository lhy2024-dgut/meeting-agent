import {
  MeetingDetail,
  MeetingSourceType,
  TranscriptResponse,
} from "@/types/api";

type SourcePreviewParams = {
  sourceType: MeetingSourceType;
  snippet: string | null | undefined;
  meeting: MeetingDetail | null | undefined;
  transcript: TranscriptResponse | null | undefined;
};

const LOCATOR_TARGET_LENGTH = 36;
const LOCATOR_MAX_LENGTH = 56;
const TRANSCRIPT_LOCATOR_TARGET_LENGTH = 24;
const TRANSCRIPT_LOCATOR_MAX_LENGTH = 32;

export function normalizeText(value: string | null | undefined): string {
  return (value ?? "")
    .normalize("NFKC")
    .toLowerCase()
    .replace(/\s+/g, " ")
    .replace(/[^\p{L}\p{N}\u4e00-\u9fff ]+/gu, "")
    .trim();
}

function collectProbes(text: string): string[] {
  const lengths = [64, 48, 32, 20, 12];
  const probes = new Set<string>();

  for (const length of lengths) {
    if (text.length < length) {
      continue;
    }
    probes.add(text.slice(0, length));
    probes.add(text.slice(Math.max(0, Math.floor((text.length - length) / 2)), Math.max(0, Math.floor((text.length - length) / 2)) + length));
    probes.add(text.slice(text.length - length));
  }

  return Array.from(probes).filter((item) => item.length >= 8);
}

function longestCommonSubstringLength(a: string, b: string): number {
  if (!a || !b) {
    return 0;
  }

  const rows = new Array(b.length + 1).fill(0);
  let best = 0;

  for (let i = 1; i <= a.length; i += 1) {
    for (let j = b.length; j >= 1; j -= 1) {
      if (a[i - 1] === b[j - 1]) {
        rows[j] = rows[j - 1] + 1;
        if (rows[j] > best) {
          best = rows[j];
        }
      } else {
        rows[j] = 0;
      }
    }
  }

  return best;
}

export function matchSnippetScore(candidate: string, snippet: string): number {
  if (!candidate || !snippet) {
    return 0;
  }

  if (candidate === snippet) {
    return snippet.length + 2000;
  }

  if (candidate.includes(snippet)) {
    return snippet.length + 1200;
  }

  if (snippet.includes(candidate)) {
    return candidate.length + 1100;
  }

  for (const probe of collectProbes(snippet)) {
    if (candidate.includes(probe)) {
      return probe.length * 12;
    }
  }

  for (const probe of collectProbes(candidate)) {
    if (snippet.includes(probe)) {
      return probe.length * 11;
    }
  }

  const lcs = longestCommonSubstringLength(candidate, snippet);
  if (lcs >= 8) {
    return lcs * 6;
  }

  return 0;
}

export function buildSourceLocatorSnippet(
  sourceType: MeetingSourceType,
  snippet: string | null | undefined,
): string | null {
  const compact = compactSourceText(snippet);
  if (!compact) {
    return null;
  }

  if (sourceType === "transcript") {
    return buildTranscriptLocatorSnippet(compact);
  }

  const clauses = splitLocatorClauses(compact);
  const bestClause = pickBestLocatorClause(clauses, sourceType);
  if (bestClause) {
    return cropLocatorClause(bestClause);
  }

  return cropLocatorClause(compact);
}

export function resolveSourcePreview({
  sourceType,
  snippet,
  meeting,
  transcript,
}: SourcePreviewParams): string | null {
  const normalizedSnippet = normalizeText(snippet);
  if (!normalizedSnippet) {
    return null;
  }

  const candidates =
    sourceType === "action_item"
      ? extractTodoItems(meeting?.action_items_text ?? "").map((text, index) => ({
          index,
          text,
          label: `待办第 ${index + 1} 条`,
        }))
      : sourceType === "resolution"
        ? extractResolutionItems(meeting?.resolutions_text ?? "").map((text, index) => ({
            index,
            text,
            label: `决议第 ${index + 1} 条`,
          }))
        : sourceType === "minutes"
          ? extractMinutesBlocks(meeting?.minutes_text ?? "").map((text, index) => ({
              index,
              text,
              label: `纪要第 ${index + 1} 段`,
            }))
          : (transcript?.segments ?? []).map((segment, index) => ({
              index,
              text: segment.text,
              label: `转录第 ${index + 1} 段`,
            }));

  let best: { label: string; score: number } | null = null;
  for (const candidate of candidates) {
    const score = matchSnippetScore(normalizeText(candidate.text), normalizedSnippet);
    if (score <= 0) {
      continue;
    }
    if (!best || score > best.score) {
      best = { label: candidate.label, score };
    }
  }

  return best?.label ?? null;
}

function compactSourceText(value: string | null | undefined): string {
  return (value ?? "").replace(/\s+/g, " ").trim();
}

function buildTranscriptLocatorSnippet(text: string): string | null {
  const cleaned = stripTranscriptSpeakerPrefix(stripTranscriptFillers(text));
  const clauses = splitLocatorClauses(cleaned)
    .map((item) => stripTranscriptSpeakerPrefix(stripTranscriptFillers(item)))
    .map((item) => item.trim())
    .filter(Boolean);

  const bestClause = pickBestTranscriptClause(clauses);
  if (bestClause) {
    return cropTranscriptLocator(bestClause);
  }

  return cropTranscriptLocator(cleaned);
}

function stripTranscriptSpeakerPrefix(text: string): string {
  return text.replace(/^[A-Za-z0-9_-]{1,24}[\uff1a:]/, "").trim();
}

function stripTranscriptFillers(text: string): string {
  return text
    .replace(/^(\u55ef|\u554a|\u8fd9\u4e2a|\u90a3\u4e2a|\u5c31\u662f|\u7136\u540e|\u5176\u5b9e|\u5bf9\u5427|\u53cd\u6b63|\u6240\u4ee5)([\uff0c,\s]+)/u, "")
    .trim();
}

function splitLocatorClauses(text: string): string[] {
  const delimiterPattern = new RegExp("[\\u3002\\uff01\\uff1f!?\\uff1b;\\n]+|[,\\uff0c]", "u");
  return text
    .split(delimiterPattern)
    .map((item) => item.trim())
    .filter(Boolean);
}

function pickBestLocatorClause(
  clauses: string[],
  sourceType: MeetingSourceType,
): string | null {
  let best: { value: string; score: number } | null = null;

  for (const clause of clauses) {
    const score = scoreLocatorClause(clause, sourceType);
    if (score <= 0) {
      continue;
    }
    if (!best || score > best.score) {
      best = { value: clause, score };
    }
  }

  return best?.value ?? null;
}

function pickBestTranscriptClause(clauses: string[]): string | null {
  let best: { value: string; score: number } | null = null;

  for (const clause of clauses) {
    const score = scoreTranscriptLocatorClause(clause);
    if (score <= 0) {
      continue;
    }
    if (!best || score > best.score) {
      best = { value: clause, score };
    }
  }

  return best?.value ?? null;
}

function scoreLocatorClause(clause: string, sourceType: MeetingSourceType): number {
  const normalized = normalizeText(clause);
  const length = normalized.length;
  if (length < 10) {
    return 0;
  }

  let score = 100 - Math.abs(length - LOCATOR_TARGET_LENGTH);
  if (length <= LOCATOR_MAX_LENGTH) {
    score += 20;
  }
  if (/\d/.test(clause)) {
    score += 4;
  }
  if (/\p{Script=Han}{2,}/u.test(clause)) {
    score += 8;
  }
  if (sourceType === "transcript" && /^[\u7532\u4e59\u4e19\u4e01][\uff1a:]/u.test(clause)) {
    score -= 12;
  }
  if (
    sourceType === "transcript" &&
    /^(\u55ef|\u554a|\u8fd9\u4e2a|\u90a3\u4e2a|\u5c31\u662f)/u.test(clause)
  ) {
    score -= 8;
  }

  return score;
}

function cropLocatorClause(text: string): string {
  if (text.length <= LOCATOR_MAX_LENGTH) {
    return text;
  }

  const normalized = normalizeText(text);
  if (normalized.length <= LOCATOR_MAX_LENGTH) {
    return text.slice(0, LOCATOR_MAX_LENGTH).trim();
  }

  const centerStart = Math.max(0, Math.floor((text.length - LOCATOR_TARGET_LENGTH) / 2));
  return text.slice(centerStart, centerStart + LOCATOR_TARGET_LENGTH).trim();
}

function scoreTranscriptLocatorClause(clause: string): number {
  const normalized = normalizeText(clause);
  const length = normalized.length;
  if (length < 8) {
    return 0;
  }

  let score = 120 - Math.abs(length - TRANSCRIPT_LOCATOR_TARGET_LENGTH) * 2;
  if (length <= TRANSCRIPT_LOCATOR_MAX_LENGTH) {
    score += 30;
  }
  if (/\p{Script=Han}{2,}/u.test(clause)) {
    score += 10;
  }
  if (/\d/.test(clause)) {
    score += 4;
  }
  if (/^(\u55ef|\u554a|\u8fd9\u4e2a|\u90a3\u4e2a|\u5c31\u662f|\u7136\u540e|\u5176\u5b9e|\u5bf9\u5427|\u53cd\u6b63|\u6240\u4ee5)/u.test(clause)) {
    score -= 16;
  }

  return score;
}

function cropTranscriptLocator(text: string): string {
  if (text.length <= TRANSCRIPT_LOCATOR_MAX_LENGTH) {
    return text.trim();
  }

  const windows = collectTranscriptLocatorWindows(text);
  let best: { value: string; score: number } | null = null;

  for (const windowText of windows) {
    const score = scoreTranscriptLocatorClause(windowText);
    if (!best || score > best.score) {
      best = { value: windowText, score };
    }
  }

  return best?.value ?? text.slice(0, TRANSCRIPT_LOCATOR_MAX_LENGTH).trim();
}

function collectTranscriptLocatorWindows(text: string): string[] {
  const windows = new Set<string>();
  const lengths = [TRANSCRIPT_LOCATOR_TARGET_LENGTH, 20, 16];

  for (const length of lengths) {
    if (text.length <= length) {
      windows.add(text.trim());
      continue;
    }

    const positions = [
      0,
      Math.max(0, Math.floor((text.length - length) / 2)),
      Math.max(0, text.length - length),
    ];

    for (const start of positions) {
      windows.add(text.slice(start, start + length).trim());
    }
  }

  return Array.from(windows).filter((item) => item.length >= 8);
}

function cleanListLine(line: string): string {
  return line
    .replace(/^[-*]\s*/, "")
    .replace(/^\d+[.)、]\s*/, "")
    .replace(/^\[[ xX]\]\s*/, "")
    .trim();
}

function extractTodoItems(text: string): string[] {
  return text
    .split("\n")
    .map((line) => cleanListLine(line.trim()))
    .filter(Boolean);
}

function extractResolutionItems(text: string): string[] {
  return text
    .split("\n")
    .map((line) => cleanListLine(line.trim()))
    .filter(Boolean);
}

function extractMinutesBlocks(text: string): string[] {
  return text
    .split(/\n\s*\n/g)
    .map((block) => block.replace(/^#+\s*/gm, "").trim())
    .filter(Boolean);
}