# Axiom Tech Corporate Knowledge Assistant — V3 Interface Direction

## Scope and status

This is the design contract for the React/Vite V3 client. It specifies intended interface behavior and does not claim that a design review, responsive test, screenshot, or production deployment has already occurred.

## Design stance

The assistant is an internal work tool, not a conversational toy. It should feel calm, precise, and evidence-led: the question is easy to ask, the answer is easy to scan, and sources are never hidden. Use a restrained product palette, a familiar sans-serif system stack, and semantic state colors. Accent color is reserved for primary actions, focus, current selection, and meaningful status.

## Primary workspace

The main view has four clear regions:

1. **Header:** product name, concise trust statement, and API/system availability.
2. **Query area:** one labelled question field, submit control, and a small set of relevant suggested questions when no result is present.
3. **Answer area:** answer summary first, then domain/specialist metadata and a compact graph-trace disclosure.
4. **Evidence area:** citations remain adjacent to the answer and show source, domain, file type, chunk, and page/section when the API supplies them.

Avoid simulated model output, invented citations, or decorative dashboards. A user should never mistake placeholder text for a verified answer.

## Required states

| State | Required behavior |
| --- | --- |
| Initial | Explain the corpus scope and offer example questions; do not fabricate an answer. |
| Submitting | Disable duplicate submission, preserve the question, expose an accessible progress message, and use content-shaped loading placeholders rather than a page-blocking spinner. |
| Answered | Put the answer before metadata; make each source independently readable and copyable. |
| Insufficient evidence | Use direct language that the corpus does not support the requested claim; show any consulted sources only when they are relevant. |
| Validation or network error | Use an inline role="alert" message, retain the draft, and provide a retry action. |
| Re-indexing | Make the action explicit, show progress/outcome, and warn that it changes the local knowledge index. |
| Offline/degraded model mode | Label deterministic/local mode accurately; do not present it as an NVIDIA-backed response. |

## Interaction and accessibility

- Every control has a visible label, keyboard access, visible focus, and disabled/loading semantics.
- The submit control works with Enter; source lists use semantic list markup and links only when a navigable locator exists.
- Announce answer, error, and ingestion-state changes without excessive live-region chatter.
- Preserve a minimum 4.5:1 contrast ratio for ordinary text, including placeholders and muted copy.
- Honor prefers-reduced-motion; use only brief state transitions (roughly 150–250 ms), never decorative entrance sequences.
- Keep answer prose comfortably readable (about 65–75 characters per line where practical) while allowing citations and metadata to wrap safely.

## Responsive behavior

- At wide widths, retain a readable answer column and a stable evidence area.
- At tablet and below, stack metadata/evidence below the answer rather than relying on cramped side panels.
- At narrow mobile widths, preserve the full query field, keep primary actions reachable, and allow long filenames, URLs, and citation locators to wrap without horizontal scrolling.

## API presentation rules

The client renders the V3 API response as data: answer, domain, specialist, citations, trace events, rewrite count, and grounding status. It must tolerate empty citation arrays, unknown future domains, and unavailable page/slide/sheet metadata. Trace detail is secondary to the answer and should be collapsible, while citations remain immediately discoverable.

## Visual vocabulary

- One consistent control shape and spacing scale across query, retry, and ingestion actions.
- Neutral content surfaces with a single accessible brand accent; success, warning, and error colors communicate state rather than decoration.
- Avoid thick side-stripe cards, gradient text, oversized rounded containers, and dense repeated card grids.
- Prefer clear headings, dividers, and source lists over nested panels.
