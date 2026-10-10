// The action log panel (FR-06, FR-35, BC-04). Each entry shows the rule ID, the dice,
// and each modifier with its cause, for the two sides. The tabletop switch hides the
// dice and the modifiers, and it leaves the rule ID and the result.

import type { LogEntry } from "../net/protocol";

export function describe(entry: LogEntry, tabletop: boolean): string {
  const data = entry.data ?? {};
  const parts: string[] = [entry.kind.replace(/_/g, " ")];
  const target = data.target ?? data.hex ?? data.to;
  if (typeof target === "string") {
    parts.push(`at ${target}`);
  }
  if (typeof data.unit === "number") {
    parts.push(`unit ${data.unit}`);
  }
  if (Array.isArray(data.units) && data.units.length > 0) {
    parts.push(`units ${(data.units as number[]).join(", ")}`);
  }
  if (typeof data.result === "string") {
    parts.push(`result ${data.result}`);
  }
  if (typeof data.firepower === "number") {
    parts.push(`${data.firepower} firepower`);
  }
  if (typeof data.odds === "string") {
    parts.push(`odds ${data.odds}, kill on ${data.kill}`);
  }
  if (!tabletop) {
    if (Array.isArray(data.dice)) {
      parts.push(`dice ${(data.dice as number[]).join(" and ")}`);
    }
    if (typeof data.die === "number") {
      parts.push(`die ${data.die}`);
    }
    if (typeof data.adjusted === "number") {
      parts.push(`adjusted ${data.adjusted}`);
    }
    const modifiers = data.modifiers;
    if (Array.isArray(modifiers) && modifiers.length > 0) {
      const text = modifiers
        .map((m) => {
          if (typeof m === "string") {
            return m;
          }
          const record = m as { value?: number; rule?: string; cause?: string };
          const sign = (record.value ?? 0) >= 0 ? "+" : "";
          return `${sign}${record.value} ${record.cause ?? ""} (${record.rule ?? ""})`.trim();
        })
        .join(", ");
      parts.push(`modifiers ${text}`);
    }
    if (typeof data.leadership === "number" && data.leadership !== 0) {
      parts.push(`leader ${data.leadership >= 0 ? "+" : ""}${data.leadership}`);
    }
    if (typeof data.morale === "number") {
      parts.push(`morale ${data.morale}`);
    }
    if (typeof data.cost_halves === "number") {
      parts.push(`${data.cost_halves / 2} movement factors`);
    }
  }
  if (typeof data.cause === "string") {
    parts.push(String(data.cause));
  }
  return parts.join(", ");
}

export function renderLog(list: HTMLOListElement, entries: LogEntry[], tabletop: boolean): void {
  list.replaceChildren();
  for (const entry of entries) {
    const item = document.createElement("li");
    const rule = document.createElement("span");
    rule.className = "rule";
    rule.textContent = entry.rule_id;
    item.append(rule, document.createTextNode(` ${describe(entry, tabletop)}`));
    list.append(item);
  }
  list.scrollTop = list.scrollHeight;
}
