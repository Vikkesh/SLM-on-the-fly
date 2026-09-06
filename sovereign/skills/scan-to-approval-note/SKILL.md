---
name: scan-to-approval-note
description: Turn extracted findings from a scanned inspection report into a formal approval note (Word, PDF or Excel) with the mandated structure, fields and tone. Use whenever an approval note, inspection write-up or sign-off document is requested.
---

# Scan to approval note

Input: transcribed findings of an inspection document plus SOP excerpts. Output: one formal document.

1. Identify asset ID, unit, inspection date and type, inspector, and every observation with reading + unit.
2. Compare each reading with the SOP limits. Say which pass and which exceed, citing the clause.
3. Risk rating: Low (all within limits) / Medium (one outside, no immediate safety impact) /
   High (immediate safety impact, or two or more outside). One sentence of justification.
4. Recommendation: "Approved for continued service" / "Approved with conditions" /
   "Not approved - corrective action required". High risk is always "Not approved".
5. Call the document tool once (generate_docx unless PDF/Excel was asked for), then reply with
   two lines: what was decided, and the saved path.

Document layout for the tool call:
- title: "Inspection Approval Note - <Asset ID>"
- metadata: Asset ID, Unit / Location, Inspection date, Inspection type, Inspector, Reference SOP,
  Risk rating, Recommendation
- sections: Purpose (1 paragraph) · Summary of findings (a table: Parameter | Reading | Limit |
  Status) · Assessment (deviations, significance, clauses) · Corrective actions (bullets with
  owner and due date, "[to be assigned]" if unknown) · Recommendation (one formal sentence)
- signoff: Inspector, Area Engineer, Approving Officer

Tone: formal, impersonal, precise. No hedging. Never invent values - write "[not stated in source]".
