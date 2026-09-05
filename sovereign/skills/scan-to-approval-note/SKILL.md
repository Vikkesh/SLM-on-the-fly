---
name: scan-to-approval-note
description: Turn extracted findings from a scanned inspection report into a formal approval note (.docx) with the mandated structure, fields and tone. Use whenever an approval note, inspection report write-up or sign-off document is requested.
---

# Scan to approval note

You have the transcribed findings of a scanned inspection document and the relevant company
context (SOP excerpts). Produce a formal approval note as a Word document.

## Steps

1. Read the findings. Identify: asset/equipment ID, location/unit, inspection date, inspector,
   inspection type, each observation with its reading and unit, and any defect or deviation.
2. Compare each reading against the limits in the company context. State clearly which are within
   limits and which exceed them. Cite the SOP clause you used.
3. Assign a risk rating: Low, Medium or High. Justify it in one sentence.
4. Decide the recommendation: "Approved for continued service", "Approved with conditions", or
   "Not approved - corrective action required".
5. Call `generate_docx` exactly once with the structure below. Do not write the document in chat.
6. Reply with a two-line summary and the saved file path returned by the tool.

## Document structure (pass to generate_docx)

- `title`: "Inspection Approval Note - <Asset ID>"
- `metadata` (in this order): Asset ID, Unit / Location, Inspection date, Inspection type,
  Inspector, Reference SOP, Risk rating, Recommendation
- `sections`:
  1. "Purpose" - one paragraph stating what was inspected and why.
  2. "Summary of findings" - bullets, one per observation, each with reading, unit and limit.
  3. "Assessment" - paragraph(s): deviations, their significance, SOP clauses relied on.
  4. "Corrective actions" - bullets with owner and due date placeholders if not given.
  5. "Recommendation" - the decision, in one formal sentence.
- `signoff`: ["Inspector", "Area Engineer", "Approving Officer"]

## Tone

Formal, impersonal, precise. Full sentences. No hedging words like "maybe" or "I think".
Never invent values; use "[not stated in source]" for anything missing.
