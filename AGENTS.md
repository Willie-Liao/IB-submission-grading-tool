# IB MYP PHE Grading Standards

This workspace is the IB MYP Physical and Health Education (PHE) grading assistant. Rubrics, grading guides, and assessment logic follow `assessment_criteria.pdf`.

Three Python scripts grade student work from pydantic schemas. Step 1 reads a rubric and builds a blank task schema. An optional learn step fills calibration notes from graded samples. Step 2 fills that schema from each student's files. Step 3 grades the filled schema and writes the comment.

## Assessment Criteria

Every assessment maps to one or more of the four IB MYP PHE criteria:

- **Criterion A: Knowing and understanding** (Max 8)
- **Criterion B: Planning for performance** (Max 8)
- **Criterion C: Applying and performing** (Max 8)
- **Criterion D: Reflecting and improving performance** (Max 8)

## Achievement Levels

Grading uses the standard IB achievement bands:

- **0**: Does not reach a standard described by any descriptors.
- **1–2**: Basic/Introductory level (e.g., "recalls", "states").
- **3–4**: Developing level (e.g., "outlines", "defines").
- **5–6**: Proficient level (e.g., "lists", "describes", "designs").
- **7–8**: Excellent level (e.g., "identifies", "constructs", "explains", "justifies").

Band 0 is a score, not a descriptor band. Descriptor bands are `1-2`, `3-4`, `5-6`, and `7-8`. When those bands share core descriptors for a task, treat them as one unit in prompts and analysis, and still write each band.

## Command Terms

Command terms set the depth of the task. Definitions are in `assessment_criteria.pdf` (pages 17-18):

- **Analyze**: Break down into essential elements.
- **Identify**: Provide an answer from possibilities.
- **Outline**: Give a brief account or summary.
- **Explain**: Give a detailed account including reasons.

## Pipeline

Python 3.10+. Dependencies: `python-docx`, `PyMuPDF`, `openai`, `python-dotenv`, `pydantic`, `langfuse`.

All three steps use MiniMax-M3 (`MINIMAX_API_KEY`, `MINIMAX_BASE_URL`, `MINIMAX_MODEL`, endpoint `https://api.minimaxi.com/v1`) at temperature 1, with thinking disabled so the reply is the JSON object. The client is OpenAI-compatible.

```
grading script/
├── models.py                    # Pydantic rubric, task, and comment schemas
├── documents.py                 # docx, text PDF, and picture PDF readers
├── pipeline.py                  # Prompt loading and validated LLM calls
├── rubric_parsing_1.py          # Step 1
├── learn_calibration.py           # Learn calibration from graded samples
├── calibrate_grading_2.py         # Step 2: fill student answers
├── grade_students_3.py            # Step 3: fill the comment
├── token_usage.py                 # Local token rollups (Langfuse usage shape)
└── prompts/pipeline/              # Instruction text for the three steps
```

Prompt wording lives in `grading script/prompts/pipeline/`. The system prompt is built once per run. Student names and submission content stay in the user message. Steps 2 and 3 send one warm-up call with `cache_warmup_user.md` before the parallel fan-out.

A response that fails pydantic validation is repaired once. The system prompt is not changed on that repair. `<think>` blocks are stripped before JSON parsing.

Unit outputs go in a dedicated subdirectory such as `grade_[X]_[Criterion]/`. A change to a rubric or prompt is applied in every script that uses it.

### Step 1: `rubric_parsing_1.py`

Reads a `.docx` or `.pdf` rubric. A picture PDF is a PDF whose every page has images and fewer than 40 alphanumeric characters. Those pages are rendered to PNG and sent to MiniMax, up to 15 pages. Text PDFs and Word files are read with PyMuPDF and python-docx.

Writes `<out>/rubric_schema.json` and `<out>/task_schema.json`. It does not grade.

- `--template` sets `template: true`. Each question keeps `template_content` separate from an empty `student_answer`. Choice menus, optional skips, repeatable lists, diagrams, and tables are fields. Strand ids come from headings such as "Criterion B, Strand i".
- `--students` is used when there is no template. The first five student folders, in sorted order, induce the same nested schema with `template: false`. Fewer than five uses all of them and prints a warning.
- If both are passed, the template wins. If neither is passed, the script exits.
- If `task_schema.json` already exists, the script exits unless `--force` is passed. Steps 2 and 3 never overwrite that shared file.

The comment skeleton is built from the rubric strands: one overall slot plus one slot per strand. Scores and comment text stay empty. `grading_sample_reference` is an empty string until the teacher sets it or runs the learn step with `--samples`. `calibration_special_case` is empty for the teacher to edit before step 2, or for the learn step to fill from graded samples. Intensity is `override`, `blend`, or `tiny_effect`. Task-level `word_count` is the required length when the task states one, otherwise null. `visual_related_submission` is true when the grader must judge a visual engagement element, such as a poster, diagram, layout, colors, or images. It is false when the task is judged from writing alone.

```bash
python "grading script/rubric_parsing_1.py" \
  --rubric path/to/rubric.docx \
  --template "grading script/prompts/Template for Criterion B.docx" \
  --out grade_9_B \
  --criterion B \
  --year 5
```

### Learn calibration: `learn_calibration.py`

Run after step 1 and before step 3 when graded sample folders should teach calibration notes. Each sample subfolder needs `comment.md` and either `content.json` or the same submission files step 2 reads. One MiniMax-M3 call reads every sample. Python writes `calibration_special_case` and `calibration_intensity` only onto fields that are still empty on the shared `task_schema.json`. Existing teacher notes stay as written. When `--students` is passed, the same empty slots are patched on every existing `content.json` under that class folder.

- `--samples` stores the folder path in `grading_sample_reference`.
- With no `--samples`, the script uses the path already in `task_schema.json`.
- An empty path exits without a model call.

```bash
python "grading script/learn_calibration.py" \
  --task-schema grade_9_B/task_schema.json \
  --samples path/to/graded_examples \
  --students grade_9_B
```

### Step 2: `calibrate_grading_2.py`

Merges every `.docx`, `.pdf`, `.png`, `.jpg`, `.jpeg`, and `.webp` in a student folder, in filename order. One MiniMax-M3 call fills `student_answer` on every field. Python copies the template side from the blank schema, counts words from `student_answer`, and leaves the comment skeleton empty. An empty answer keeps `word_count` null.

Picture-PDF submissions use page images. Student sends are capped at 5 images. Text and images stay in document order. The call is skipped when `content.json` already exists. Progress is written to `step2_fill_checkpoints`. That folder records which files were read and token totals for that student's calls. It does not decide whether a student is skipped.

`content.json` stores the filled task schema and a comparison that keeps the worksheet prompt apart from the student's answer. For a choice, the comparison shows the menu as template content and only the marked option as the student's answer. When `visual_related_submission` is true, the visual field describes layout, colors, images, and composition without scoring them. When it is false, the fill does not describe how the page looks. Only work for the criterion being graded goes into `student_answer`.

```bash
python "grading script/calibrate_grading_2.py" \
  --students grade_9_B \
  --task-schema grade_9_B/task_schema.json
```

### Step 3: `grade_students_3.py`

Text only. It does not open the submission files again. The system prompt holds the rubric schema, the comment headings, and the calibration intensities:

- `override` replaces the rubric for that field
- `blend` applies the rubric and the special case together
- `tiny_effect` lets the rubric set the band and the special case change wording only
- an empty special case uses the rubric only
- a non-empty special case with no intensity is `blend`

The model returns the comment object only. Headings must match `task_schema.json`. Scores are integers from 0 to 8. Strand comments cite `student_answer`, not `template_content`. When `visual_related_submission` is true, visual engagement is judged from the layout, colors, images, and composition described in `student_answer`. When it is false, visual appearance is not scored. The script writes the comment back into `content.json` and renders `comment.md`. It does not rewrite `template_content`, `choices`, `columns`, or `student_answer`. Students who already have `comment.md` are skipped. Progress is written to `step3_grade_checkpoints`, including the overall score and token totals for that student's calls.

MiniMax token usage is stored in Langfuse usage shape (`input`, `output`, `total`, `calls`). Each student checkpoint JSON includes that student's tokens for the step. The class folder also gets `token_usage.json` with per-step totals, per-student step 2 and step 3 totals, and a run total. Langfuse tracing stays off; nothing is exported. Warm-up calls count toward the step total, not toward a student row. `token_usage.json` is gitignored.

Template wording is not evidence. Unselected menu options, column headers, and printed examples are not the student's writing.

```bash
python "grading script/grade_students_3.py" \
  --students grade_9_B \
  --rubric-schema grade_9_B/rubric_schema.json \
  --task-schema grade_9_B/task_schema.json
```

## Guidelines for Grading Guides

When `rubric_parsing_1.py` builds a rubric schema:

1. **Consistency**: Descriptors for each band match the year level (Year 1, 3, or 5) specified in the task.
2. **Observable Indicators**: Translate the broad IB descriptors into concrete, task-specific observable indicators (e.g., "Student identifies 3 goals" for a 7-8 in Criterion B).
3. **Strand Alignment**: Each strand of the criterion is addressed, and each task-schema part lists the strand ids it maps to.

## Example Alignment

```markdown
# Criterion B: Planning for performance (Year 5 Example)
- **7–8**: The student **develops** goals to enhance performance and **designs, explains and justifies** a plan to improve physical performance and health.
- **5–6**: The student **explains** goals to enhance performance and **designs and explains** a plan to improve physical performance and health.
```

Refer to `assessment_criteria.pdf` for the exact wording of descriptors for each Year group.
