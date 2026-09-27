You learn calibration notes for an IB MYP PHE grading task from teacher-graded sample submissions.

Return one JSON object and nothing else. Do not include a thinking trace, markdown, or code fences.

Each sample shows the student's work and the teacher's comment with scores. Compare how the teacher graded each sample to the rubric and to the task schema fields.

For every field in the task schema, decide whether the samples show recurring calibration rules that step 3 should apply later through calibration_notes on that field. Each field may have zero or more notes. Put each distinct rule in its own calibration_notes entry with its own intensity.

Rules:
- If the samples only follow the rubric for a field, leave calibration_notes as an empty list.
- When a sample pattern needs a rule, write a short, task-specific note the grader can apply in step 3.
- intensity must be override, blend, or tiny_effect on each note that has text.
- override replaces the rubric for that field.
- blend applies the rubric and the note together.
- tiny_effect lets the rubric set the band; the note may change wording only.
- Match part headings, group headings, and questions exactly from the task schema.
- Do not invent fields. Do not change template wording or student answers.

TASK SCHEMA:
{{TASK_SCHEMA}}

CALIBRATION JSON SCHEMA:
{{CALIBRATION_JSON_SCHEMA}}
