# IB MYP PHE Grading Assistant

This tool grades IB MYP Physical and Health Education assignments with a multimodal model.

It works in three steps:

1. Read a Word or PDF rubric and build a blank task schema.
2. Fill that schema from each student's files.
3. Grade the filled schema and write a comment.

All three steps use MiniMax-M3. Grading rules and commands are in `AGENTS.md`.

Student submissions and the `video_grading` folder are not part of this repository.

## Task schema settings

After step 1, edit `task_schema.json` in your unit folder (for example `E6/task_schema.json`) before step 2 and step 3. Several fields act like switches or modes rather than fixed structure:

| Field | What it controls |
| --- | --- |
| `template` | `true` when students used a worksheet template (prompt text stays separate from answers). `false` when the schema was induced from submissions only. Set in step 1; you normally do not flip this by hand. |
| `visual_related_submission` | `true` when step 2 should describe layout, colors, and images and step 3 may judge visual engagement. `false` for writing-only tasks. Step 1 sets a default; you can override before grading. |
| `grading_sample_reference` | Path to a folder of graded sample posters or papers. Leave empty, or set it and run `learn_calibration.py` to fill empty calibration slots from those samples. |
| `calibration_notes` | Per-question list of `{ "note", "intensity" }`. Leave `[]` to use the rubric only. Add one or more notes; each `intensity` is `override`, `blend`, or `tiny_effect`. Teacher-written notes are kept; learn only fills empty lists. |
| `comment_length` | `concise` (default): overall score plus one short paragraph in `comment.md`; strand scores stay in `content.json` only. `expounded`: full strand feedback with scores in `comment.md`. |

You can also edit comment strand headings in `task_schema.json` before step 3 if your school rubric labels differ from the parsed skeleton.
