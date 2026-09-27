"""Pydantic schemas for the three-step grading pipeline."""

from __future__ import annotations

import json
import re
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

DESCRIPTOR_BANDS = {"1-2", "3-4", "5-6", "7-8"}
OVERALL_HEADING = "Overall achievement"


class CalibrationIntensity(str, Enum):
    override = "override"
    blend = "blend"
    tiny_effect = "tiny_effect"


class AnswerKind(str, Enum):
    text = "text"
    choice = "choice"
    list = "list"
    table = "table"
    diagram = "diagram"


class SectionField(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str
    template_content: str = ""
    student_answer: str = ""
    answer_kind: AnswerKind = AnswerKind.text
    choices: list[str] = Field(default_factory=list)
    columns: list[str] = Field(default_factory=list)
    optional: bool = False
    repeatable: bool = False
    calibration_special_case: str = ""
    calibration_intensity: CalibrationIntensity | None = None
    word_count: int | None = None


class SectionGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    heading: str
    template_content: str = ""
    fields: list[SectionField]


class Part(BaseModel):
    model_config = ConfigDict(extra="forbid")

    heading: str
    rubric_strand_ids: list[str] = Field(default_factory=list)
    template_content: str = ""
    groups: list[SectionGroup]


class CommentSlot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    heading: str
    score: int | None = None
    max_score: int = 8
    text: str = ""

    @field_validator("score")
    @classmethod
    def score_in_range(cls, value: int | None) -> int | None:
        if value is not None and not 0 <= value <= 8:
            raise ValueError("score must be an integer from 0 to 8")
        return value


class CommentFormat(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overall: CommentSlot
    strands: list[CommentSlot]
    strengths: str = ""
    improvements: str = ""


class TaskSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grading_sample_reference: str = ""
    template: bool
    title: str = ""
    parts: list[Part]
    word_count: int | None = None
    visual_related_submission: bool = False
    comment: CommentFormat


class TaskSchemaDraft(BaseModel):
    """Step 1 model output. The comment skeleton is attached in Python."""

    model_config = ConfigDict(extra="ignore")

    grading_sample_reference: str = ""
    template: bool = False
    title: str = ""
    parts: list[Part]
    word_count: int | None = None
    visual_related_submission: bool = False


class AnswerUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    question: str
    student_answer: str


class AnswerGroup(BaseModel):
    model_config = ConfigDict(extra="ignore")

    heading: str
    fields: list[AnswerUpdate]


class AnswerPart(BaseModel):
    model_config = ConfigDict(extra="ignore")

    heading: str
    groups: list[AnswerGroup]


class AnswerFill(BaseModel):
    """Step 2 response. Only student_answer is copied onto the task schema."""

    model_config = ConfigDict(extra="ignore")

    parts: list[AnswerPart]


class CalibrationFieldLearn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    question: str
    calibration_special_case: str = ""
    calibration_intensity: CalibrationIntensity | None = None


class CalibrationGroupLearn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    heading: str
    fields: list[CalibrationFieldLearn]


class CalibrationPartLearn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    heading: str
    groups: list[CalibrationGroupLearn]


class CalibrationLearn(BaseModel):
    """Learn step response. Only calibration fields are merged onto the task schema."""

    model_config = ConfigDict(extra="ignore")

    parts: list[CalibrationPartLearn]


class StudentContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task: TaskSchema
    comparison: str


class LevelNote(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = ""
    movement_requirements: str = ""
    notes: str = ""


class AssignmentOverview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_summary: str = ""
    criterion: str = ""
    grade_or_year: str = ""
    levels: list[LevelNote] = Field(default_factory=list)


class SubmissionRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item: str = ""
    applies_to_levels: list[str] = Field(default_factory=list)
    detail: str = ""


class RubricBand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    band: str
    descriptor: str = ""

    @field_validator("band")
    @classmethod
    def descriptor_band(cls, value: str) -> str:
        normalized = value.replace("–", "-").replace("—", "-").strip()
        if normalized not in DESCRIPTOR_BANDS:
            raise ValueError(
                "band must be one of 1-2, 3-4, 5-6, 7-8. "
                "Band 0 is a score, not a descriptor band."
            )
        return normalized


class RubricStrand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str = ""
    bands: list[RubricBand] = Field(min_length=1)


class RubricBreakdown(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bands_share_core_descriptors: bool = True
    strands: list[RubricStrand] = Field(min_length=1)


class LevelGradingNote(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: str = ""
    what_to_look_for: str = ""


class GraderChecklist(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: str = ""
    items: list[str] = Field(default_factory=list)


class RedFlag(BaseModel):
    model_config = ConfigDict(extra="forbid")

    issue: str = ""
    effect_on_grade: str = ""


class RubricSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assignment_overview: AssignmentOverview
    submission_requirements: list[SubmissionRequirement] = Field(default_factory=list)
    rubric_breakdown: RubricBreakdown
    level_specific_grading_notes: list[LevelGradingNote] = Field(default_factory=list)
    grader_checklist: list[GraderChecklist] = Field(default_factory=list)
    red_flags: list[RedFlag] = Field(default_factory=list)


def schema_json(model: type[BaseModel]) -> str:
    return json.dumps(model.model_json_schema(), indent=2, ensure_ascii=False)


def dump_model(model: BaseModel) -> str:
    return json.dumps(model.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"


def extract_json_object(raw: str) -> Any:
    cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("Response does not contain a JSON object.")
    return json.loads(cleaned[start : end + 1])


def count_words(text: str) -> int | None:
    words = text.split()
    if not words:
        return None
    return len(words)


def strand_heading(strand: RubricStrand) -> str:
    if strand.name.strip():
        return f"Strand {strand.id}: {strand.name.strip()}"
    return f"Strand {strand.id}"


def build_comment_skeleton(rubric: RubricSchema) -> CommentFormat:
    strands = [
        CommentSlot(heading=strand_heading(strand), score=None, max_score=8, text="")
        for strand in rubric.rubric_breakdown.strands
    ]
    if not strands:
        raise ValueError("Rubric schema has no strands to build a comment skeleton.")
    return CommentFormat(
        overall=CommentSlot(heading=OVERALL_HEADING, score=None, max_score=8, text=""),
        strands=strands,
        strengths="",
        improvements="",
    )


_VISUAL_TERMS = (
    "visual",
    "layout",
    "poster",
    "diagram",
    "drawing",
    "illustration",
    "fonts",
    "colors",
    "images",
    "engagement",
)


def _text_needs_visual(text: str) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in _VISUAL_TERMS)


def submission_needs_visual(draft: TaskSchemaDraft, rubric: RubricSchema) -> bool:
    """True when step 3 must judge a visual engagement element."""
    if draft.visual_related_submission:
        return True
    for part in draft.parts:
        for group in part.groups:
            for field in group.fields:
                if field.answer_kind == AnswerKind.diagram:
                    return True
                if _text_needs_visual(field.question) or _text_needs_visual(field.template_content):
                    return True
    overview = rubric.assignment_overview.task_summary
    if _text_needs_visual(overview):
        return True
    for strand in rubric.rubric_breakdown.strands:
        if _text_needs_visual(strand.name):
            return True
        if any(_text_needs_visual(band.descriptor) for band in strand.bands):
            return True
    return False


def finalize_task_schema(
    draft: TaskSchemaDraft,
    rubric: RubricSchema,
    *,
    template: bool,
) -> TaskSchema:
    """Clear student answers and attach the comment skeleton from the rubric."""
    if not draft.parts:
        raise ValueError("Task schema has no parts.")
    task = TaskSchema(
        grading_sample_reference=draft.grading_sample_reference,
        template=template,
        title=draft.title,
        parts=draft.parts,
        word_count=draft.word_count,
        visual_related_submission=submission_needs_visual(draft, rubric),
        comment=build_comment_skeleton(rubric),
    )
    for part in task.parts:
        if not template:
            part.template_content = ""
        for group in part.groups:
            if not template:
                group.template_content = ""
            if not group.fields:
                raise ValueError(f"Group {group.heading!r} has no fields.")
            for field in group.fields:
                field.student_answer = ""
                field.word_count = None
                field.calibration_special_case = ""
                field.calibration_intensity = None
                if not template:
                    field.template_content = ""
    return task


def merge_student_answers(blank: TaskSchema, filled: AnswerFill) -> TaskSchema:
    """Copy student_answer onto the blank schema and count words in Python."""
    if len(blank.parts) != len(filled.parts):
        raise ValueError(
            f"Expected {len(blank.parts)} parts, got {len(filled.parts)}."
        )
    task = blank.model_copy(deep=True)
    for part, update in zip(task.parts, filled.parts):
        if part.heading != update.heading:
            raise ValueError(
                f"Part heading {update.heading!r} does not match {part.heading!r}."
            )
        if len(part.groups) != len(update.groups):
            raise ValueError(
                f"Part {part.heading!r}: expected {len(part.groups)} groups, "
                f"got {len(update.groups)}."
            )
        for group, group_update in zip(part.groups, update.groups):
            if group.heading != group_update.heading:
                raise ValueError(
                    f"Group heading {group_update.heading!r} does not match {group.heading!r}."
                )
            if len(group.fields) != len(group_update.fields):
                raise ValueError(
                    f"Group {group.heading!r}: expected {len(group.fields)} fields, "
                    f"got {len(group_update.fields)}."
                )
            for field, field_update in zip(group.fields, group_update.fields):
                if field.question != field_update.question:
                    raise ValueError(
                        f"Question {field_update.question!r} does not match {field.question!r}."
                    )
                field.student_answer = field_update.student_answer
                field.word_count = count_words(field.student_answer)
    task.comment = blank.comment.model_copy(deep=True)
    return task


def merge_learned_calibration(task: TaskSchema, learned: CalibrationLearn) -> int:
    """Copy learned calibration onto empty field slots. Returns the number of fields updated."""
    if len(task.parts) != len(learned.parts):
        raise ValueError(
            f"Expected {len(task.parts)} parts, got {len(learned.parts)}."
        )
    updated = 0
    for part, part_learn in zip(task.parts, learned.parts):
        if part.heading != part_learn.heading:
            raise ValueError(
                f"Part heading {part_learn.heading!r} does not match {part.heading!r}."
            )
        if len(part.groups) != len(part_learn.groups):
            raise ValueError(
                f"Part {part.heading!r}: expected {len(part.groups)} groups, "
                f"got {len(part_learn.groups)}."
            )
        for group, group_learn in zip(part.groups, part_learn.groups):
            if group.heading != group_learn.heading:
                raise ValueError(
                    f"Group heading {group_learn.heading!r} does not match {group.heading!r}."
                )
            if len(group.fields) != len(group_learn.fields):
                raise ValueError(
                    f"Group {group.heading!r}: expected {len(group.fields)} fields, "
                    f"got {len(group_learn.fields)}."
                )
            for field, field_learn in zip(group.fields, group_learn.fields):
                if field.question != field_learn.question:
                    raise ValueError(
                        f"Question {field_learn.question!r} does not match {field.question!r}."
                    )
                if field.calibration_special_case.strip():
                    continue
                note = field_learn.calibration_special_case.strip()
                if not note:
                    continue
                field.calibration_special_case = note
                field.calibration_intensity = field_learn.calibration_intensity
                updated += 1
    return updated


def render_comparison(task: TaskSchema, *, include_grading_details: bool = False) -> str:
    blocks: list[str] = []
    for part in task.parts:
        strand = ", ".join(part.rubric_strand_ids)
        title = f"{part.heading} (strand {strand})" if strand else part.heading
        for group in part.groups:
            for field in group.fields:
                template = field.template_content.strip()
                if field.choices:
                    menu = "; ".join(field.choices)
                    template = f"{template}: {menu}" if template else menu
                if field.columns:
                    columns = "; ".join(field.columns)
                    column_line = f"Columns: {columns}"
                    template = f"{template} {column_line}".strip() if template else column_line
                lines = [
                    title,
                    group.heading,
                    field.question,
                    f"template content: {template}",
                    f"student's answer: {field.student_answer}",
                ]
                if include_grading_details:
                    shown = "null" if field.word_count is None else str(field.word_count)
                    lines.append(f"word_count: {shown}")
                    if field.calibration_special_case.strip():
                        intensity = (
                            field.calibration_intensity.value
                            if field.calibration_intensity
                            else CalibrationIntensity.blend.value
                        )
                        lines.append(
                            f"calibration_special_case: {field.calibration_special_case}"
                        )
                        lines.append(f"calibration_intensity: {intensity}")
                blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def assert_comment_matches(filled: CommentFormat, skeleton: CommentFormat) -> None:
    if filled.overall.heading != skeleton.overall.heading:
        raise ValueError(
            f"Overall heading {filled.overall.heading!r} does not match "
            f"skeleton heading {skeleton.overall.heading!r}."
        )
    if filled.overall.score is None:
        raise ValueError("Overall score is empty.")
    if filled.overall.max_score != skeleton.overall.max_score:
        raise ValueError("Overall max_score does not match the skeleton.")
    if len(filled.strands) != len(skeleton.strands):
        raise ValueError(
            f"Expected {len(skeleton.strands)} strand comments, got {len(filled.strands)}."
        )
    for got, expected in zip(filled.strands, skeleton.strands):
        if got.heading != expected.heading:
            raise ValueError(
                f"Comment heading {got.heading!r} does not match "
                f"skeleton heading {expected.heading!r}."
            )
        if got.score is None:
            raise ValueError(f"Score is empty for {got.heading}.")
        if got.max_score != expected.max_score:
            raise ValueError(f"max_score does not match the skeleton for {got.heading}.")


def render_comment_md(student_name: str, comment: CommentFormat) -> str:
    if comment.overall.score is None:
        raise ValueError("Overall score is empty.")
    lines = [
        f"{student_name}, your overall achievement score: {comment.overall.score}/{comment.overall.max_score}",
        "",
    ]
    for slot in comment.strands:
        if slot.score is None:
            raise ValueError(f"Score is empty for {slot.heading}.")
        lines.append(f"{slot.heading}: {slot.score}/{slot.max_score}")
        lines.append(slot.text)
        lines.append("")
    lines.append(f"What you did well: {comment.strengths}")
    lines.append("")
    lines.append(f"What to improve: {comment.improvements}")
    lines.append("")
    return "\n".join(lines)
