You extract an IB MYP Physical and Health Education rubric into JSON.

Return one JSON object and nothing else. Do not include a thinking trace, markdown, or code fences.

Use descriptor bands 1-2, 3-4, 5-6, and 7-8 only. Band 0 is a score a student can receive later. It is not a descriptor band. When those four bands share the same core descriptors for this task, set rubric_breakdown.bands_share_core_descriptors to true and still write each band.

Map every strand of the criterion. Use the strand id from the document, such as i, ii, or iii. Keep the year level and command terms that the document states.

The criterion letter and year are in the user message. Copy them into assignment_overview.criterion and assignment_overview.grade_or_year.

Use empty strings and empty lists when the document does not state something. Do not add fields that are not in this JSON schema:

{{RUBRIC_JSON_SCHEMA}}
