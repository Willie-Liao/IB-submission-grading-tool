You learn calibration notes for an IB MYP PHE grading task from teacher-graded sample submissions.

Return one JSON object and nothing else. Do not include a thinking trace, markdown, or code fences.

Each sample shows the student's work and the teacher's comment with scores. Compare how the teacher graded each sample to the rubric and to the task schema fields.

For every field in the task schema, decide whether the samples show a recurring calibration rule that step 3 should apply later through calibration_special_case and calibration_intensity on that field.

Rules:
- If the samples only follow the rubric for a field, leave calibration_special_case as an empty string and calibration_intensity as null.
- When a sample pattern needs a rule, write a short, task-specific calibration_special_case the grader can apply in step 3.
- calibration_intensity must be override, blend, or tiny_effect when calibration_special_case is non-empty.
- override replaces the rubric for that field.
- blend applies the rubric and the special case together.
- tiny_effect lets the rubric set the band; the special case may change wording only.
- Match part headings, group headings, and questions exactly from the task schema.
- Do not invent fields. Do not change template wording or student answers.

TASK SCHEMA:
{{TASK_SCHEMA}}

CALIBRATION JSON SCHEMA:
{{CALIBRATION_JSON_SCHEMA}}
