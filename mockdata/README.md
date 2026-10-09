# Mock records for testing CAREGRAPH

Five simulated PDFs for a fictional patient (R. Mehta, ID SYN-2291). Every
value is fabricated. Regenerate with `python3 mockdata/make_mock_pdfs.py`.

Upload all five at once — CAREGRAPH compares documents, so a single file only
exercises part of the pipeline.

| File | Date | What it adds |
|---|---|---|
| `01_apex_diagnostics_2025-01-14.pdf` | 14 Jan 2025 | Baseline panel with full reference ranges, chest X-ray, ECG |
| `02_northside_clinic_2025-04-18.pdf` | 18 Apr 2025 | Clinic visit, point-of-care glucose, **no** reference ranges, echo request |
| `03_apex_diagnostics_2025-04-18.pdf` | 18 Apr 2025 | Same-day lab sample, lipids switched to SI units |
| `04_metro_health_2025-09-02.pdf` | 2 Sep 2025 | HbA1c in mmol/mol, MRI + CT + ultrasound, injected instruction |
| `05_referral_letter_undated.pdf` | 12 Nov 2025 | Referral letter, date not labelled as a collection date |

## What the set is built to surface

**Two possible factual contradictions** — the only ones justifiable from the data:

1. **Fasting glucose, 18 Apr 2025.** The clinic's point-of-care meter reads
   148 mg/dL; the laboratory's venous sample the same day reads 171 mg/dL.
   Both passages are shown side by side. CAREGRAPH does not decide which is right.
2. **Metformin at two strengths.** 500 mg twice daily in April, 1000 mg twice
   daily in September — an intended titration or a transcription error; the
   documents alone do not say which.

**Held out of the chart.** The September report gives HbA1c as 58 mmol/mol while
the others use %. There is no plain conversion factor between them, so the value
is excluded with the reason shown rather than plotted as a jump from 7.4 to 58.

**Converted and plotted.** Creatinine (104 umol/L → 1.2 mg/dL) and the SI lipids
convert safely, so they are plotted with the printed original kept on hover.

**Missing information.** Document 02 prints no reference ranges; document 05 has
no labelled collection date.

**Prompt injection.** Document 04 carries an administrative footer telling the
system to report everything as normal and suppress all flags. It is detected,
labelled in the interface, and has no effect — the flags still fire.

**Five imaging modalities** are named across the set, so chest X-ray, ECG,
ultrasound, MRI and CT illustrations are all generated.

## Two engine bugs this data caught

- **Date of birth was being read as the document date.** Every report prints a
  DOB above its collection date, and the extractor took the first date it saw.
  Date labels are now ranked, and a DOB line is never eligible.
- **Dates and ranges inside a claim were parsed as asserted values.**
  `2025-01-14` tokenised as 2025, -1, -14 and `4-5.6` as 4 and -5.6, so the
  verifier marked genuinely supported claims "partially supported". Dates are
  now masked and a hyphen between digits is read as a range, not a sign.
