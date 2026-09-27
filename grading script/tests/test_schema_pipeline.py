"""API-free checks for the schema pipeline."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import fitz
from pydantic import ValidationError

SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

from documents import (  # noqa: E402
    document_text,
    extract_pdf_text,
    is_picture_pdf,
    load_rubric_or_template,
)
from models import (  # noqa: E402
    AnswerKind,
    AnswerFill,
    AnswerGroup,
    AnswerPart,
    AnswerUpdate,
    CommentFormat,
    CommentSlot,
    LevelNote,
    RubricBand,
    RubricBreakdown,
    RubricSchema,
    RubricStrand,
    TaskSchema,
    TaskSchemaDraft,
    assert_comment_matches,
    build_comment_skeleton,
    count_words,
    finalize_task_schema,
    merge_student_answers,
    render_comment_md,
    render_comparison,
)


def rubric_with_strands(*strand_ids: str) -> RubricSchema:
    return RubricSchema(
        assignment_overview={
            "task_summary": "Design a game",
            "criterion": "B",
            "grade_or_year": "5",
            "levels": [LevelNote(name="Year 5")],
        },
        rubric_breakdown=RubricBreakdown(
            strands=[
                RubricStrand(
                    id=strand_id,
                    bands=[RubricBand(band="5-6", descriptor="designs and explains")],
                )
                for strand_id in strand_ids
            ]
        ),
    )


def game_plan_task() -> TaskSchema:
    return TaskSchema(
        template=True,
        title="Game Creation Plan",
        word_count=None,
        comment=CommentFormat(
            overall=CommentSlot(heading="Overall achievement"),
            strands=[
                CommentSlot(heading="Strand i"),
                CommentSlot(heading="Strand ii"),
            ],
        ),
        parts=[
            {
                "heading": "Part 1: Designing Your Game",
                "rubric_strand_ids": ["i"],
                "template_content": "Your goal is to design and explain a plan for a new game.",
                "groups": [
                    {
                        "heading": "A. Outline of the game",
                        "fields": [
                            {
                                "question": "2. Game Type",
                                "answer_kind": "choice",
                                "template_content": "Please circle or highlight one",
                                "choices": [
                                    "Tag & Evasion Game",
                                    "Invasion Game",
                                    "Fielding & Striking Game",
                                    "Net & Wall Game",
                                    "Target Game",
                                    "Cooperative Game",
                                ],
                            },
                            {
                                "question": "5. Space (Boundary) & Set-Up",
                                "answer_kind": "diagram",
                                "template_content": "Describe the playing area and draw a simple diagram.",
                            },
                            {
                                "question": "8. Rules",
                                "answer_kind": "list",
                                "repeatable": True,
                                "template_content": "List the rules. Number of rules varies.",
                            },
                        ],
                    },
                    {
                        "heading": "B. Game Dynamics & Player Experience",
                        "fields": [
                            {
                                "question": "Defending Tactics",
                                "optional": True,
                                "template_content": "Skip this part if your game has no direct defending.",
                            }
                        ],
                    },
                ],
            },
            {
                "heading": "Part 2: Reflecting on Your Design Process",
                "rubric_strand_ids": ["ii"],
                "groups": [
                    {
                        "heading": "2. Internal peer feedback",
                        "fields": [
                            {
                                "question": "Peer feedback",
                                "answer_kind": "table",
                                "columns": [
                                    "Teammate's Name",
                                    "Contributed new, original ideas",
                                    "Helped solve problems",
                                    "Listened respectfully; communicated clearly",
                                    "Stayed on-task; did their share",
                                    "Overall Contribution",
                                ],
                                "template_content": "Rate each teammate. Column scales printed on the sheet are /5 and overall /100.",
                            }
                        ],
                    }
                ],
            },
        ],
    )


class SchemaTests(unittest.TestCase):
    def test_game_plan_round_trip(self) -> None:
        task = game_plan_task()
        restored = TaskSchema.model_validate(task.model_dump())
        self.assertTrue(restored.template)
        self.assertIsNone(restored.word_count)
        game_type = restored.parts[0].groups[0].fields[0]
        self.assertEqual(game_type.answer_kind.value, "choice")
        self.assertEqual(len(game_type.choices), 6)
        self.assertTrue(restored.parts[0].groups[1].fields[0].optional)
        rules = restored.parts[0].groups[0].fields[2]
        self.assertTrue(rules.repeatable)
        self.assertEqual(rules.answer_kind.value, "list")
        self.assertEqual(restored.parts[0].groups[0].fields[1].answer_kind.value, "diagram")
        peer = restored.parts[1].groups[0].fields[0]
        self.assertEqual(peer.answer_kind.value, "table")
        self.assertEqual(len(peer.columns), 6)

    def test_word_count(self) -> None:
        self.assertEqual(count_words("Invasion Game"), 2)
        self.assertIsNone(count_words(""))
        self.assertIsNone(count_words("   "))

    def test_merge_counts_words_and_keeps_template(self) -> None:
        blank = game_plan_task()
        filled = AnswerFill(
            parts=[
                AnswerPart(
                    heading="Part 1: Designing Your Game",
                    groups=[
                        AnswerGroup(
                            heading="A. Outline of the game",
                            fields=[
                                AnswerUpdate(question="2. Game Type", student_answer="Invasion Game"),
                                AnswerUpdate(question="5. Space (Boundary) & Set-Up", student_answer=""),
                                AnswerUpdate(question="8. Rules", student_answer="No running with the ball"),
                            ],
                        ),
                        AnswerGroup(
                            heading="B. Game Dynamics & Player Experience",
                            fields=[AnswerUpdate(question="Defending Tactics", student_answer="")],
                        ),
                    ],
                ),
                AnswerPart(
                    heading="Part 2: Reflecting on Your Design Process",
                    groups=[
                        AnswerGroup(
                            heading="2. Internal peer feedback",
                            fields=[AnswerUpdate(question="Peer feedback", student_answer="Alex 5 4 5 5 90")],
                        )
                    ],
                ),
            ]
        )
        merged = merge_student_answers(blank, filled)
        game_type = merged.parts[0].groups[0].fields[0]
        self.assertEqual(game_type.student_answer, "Invasion Game")
        self.assertEqual(game_type.word_count, 2)
        self.assertEqual(game_type.choices[1], "Invasion Game")
        self.assertEqual(blank.parts[0].groups[0].fields[0].student_answer, "")
        self.assertIsNone(merged.parts[0].groups[0].fields[1].word_count)
        self.assertIsNone(merged.comment.overall.score)
        comparison = render_comparison(merged)
        self.assertIn("template content: Please circle or highlight one: Tag & Evasion Game; Invasion Game", comparison)
        self.assertIn("student's answer: Invasion Game", comparison)

    def test_comment_heading_and_score(self) -> None:
        skeleton = game_plan_task().comment
        with self.assertRaises(ValidationError):
            CommentSlot(heading="Strand i", score=9)
        mismatched = CommentFormat(
            overall=CommentSlot(heading="Overall achievement", score=6, text="Fine"),
            strands=[
                CommentSlot(heading="Strand iii", score=6, text="Wrong heading"),
                CommentSlot(heading="Strand ii", score=5, text="Ok"),
            ],
        )
        with self.assertRaises(ValueError):
            assert_comment_matches(mismatched, skeleton)
        matched = CommentFormat(
            overall=CommentSlot(
                heading="Overall achievement",
                score=6,
                text="The plan is specific enough to play.",
            ),
            strands=[
                CommentSlot(heading="Strand i", score=6, text="The student selected Invasion Game."),
                CommentSlot(heading="Strand ii", score=5, text="The reflection names one rule change."),
            ],
            strengths="Clear winning condition.",
            improvements="Explain why the rule change helps.",
        )
        assert_comment_matches(matched, skeleton)
        rendered = render_comment_md("Jun", matched)
        self.assertIn("Jun, your overall achievement score: 6/8", rendered)
        self.assertIn("Strand i: 6/8", rendered)
        self.assertIn("What you did well: Clear winning condition.", rendered)
        self.assertIn("What to improve: Explain why the rule change helps.", rendered)

    def test_finalize_clears_answers_and_builds_comments(self) -> None:
        draft = TaskSchemaDraft.model_validate(
            {
                "template": True,
                "title": "Game Creation Plan",
                "word_count": None,
                "parts": [
                    {
                        "heading": "Part 1",
                        "rubric_strand_ids": ["i"],
                        "template_content": "Design a game",
                        "groups": [
                            {
                                "heading": "A",
                                "fields": [
                                    {
                                        "question": "Name",
                                        "student_answer": "copied from a sample",
                                        "template_content": "Name of your game",
                                        "calibration_special_case": "old note",
                                        "word_count": 4,
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        )
        task = finalize_task_schema(draft, rubric_with_strands("i", "ii"), template=True)
        field = task.parts[0].groups[0].fields[0]
        self.assertEqual(field.student_answer, "")
        self.assertIsNone(field.word_count)
        self.assertEqual(field.calibration_special_case, "")
        self.assertEqual(field.template_content, "Name of your game")
        self.assertEqual(task.comment.overall.heading, "Overall achievement")
        self.assertEqual([slot.heading for slot in task.comment.strands], ["Strand i", "Strand ii"])
        self.assertIsNone(task.comment.overall.score)
        self.assertFalse(task.visual_related_submission)

    def test_visual_flag_turns_on_for_a_diagram_or_visual_rubric(self) -> None:
        written = TaskSchemaDraft.model_validate(
            {
                "template": False,
                "parts": [
                    {
                        "heading": "Reflection",
                        "groups": [
                            {
                                "heading": "A",
                                "fields": [{"question": "What changed", "answer_kind": "text"}],
                            }
                        ],
                    }
                ],
            }
        )
        quiet = finalize_task_schema(written, rubric_with_strands("i"), template=False)
        self.assertFalse(quiet.visual_related_submission)

        drawn = TaskSchemaDraft.model_validate(
            {
                "template": True,
                "visual_related_submission": False,
                "parts": [
                    {
                        "heading": "Plan",
                        "groups": [
                            {
                                "heading": "A",
                                "fields": [
                                    {
                                        "question": "Space and set-up",
                                        "answer_kind": "diagram",
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        )
        self.assertEqual(drawn.parts[0].groups[0].fields[0].answer_kind, AnswerKind.diagram)
        visual = finalize_task_schema(drawn, rubric_with_strands("i"), template=True)
        self.assertTrue(visual.visual_related_submission)

        poster = RubricSchema.model_validate(
            {
                "assignment_overview": {"task_summary": "Make a values poster"},
                "rubric_breakdown": {
                    "strands": [
                        {
                            "id": "ii",
                            "name": "Visual Presentation",
                            "bands": [{"band": "5-6", "descriptor": "The poster is visually appealing."}],
                        }
                    ]
                },
            }
        )
        flagged = finalize_task_schema(written, poster, template=False)
        self.assertTrue(flagged.visual_related_submission)
        skeleton = build_comment_skeleton(rubric_with_strands("i"))
        self.assertEqual(skeleton.strands[0].heading, "Strand i")

    def test_band_zero_is_not_a_descriptor(self) -> None:
        with self.assertRaises(ValidationError):
            RubricBand(band="0", descriptor="no evidence")


class DocumentTests(unittest.TestCase):
    def test_text_pdf_and_picture_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            text_pdf = root / "text.pdf"
            document = fitz.open()
            page = document.new_page()
            page.insert_text(
                (72, 72),
                "This rubric page has more than forty alphanumeric characters for the reader.",
            )
            document.save(text_pdf)
            document.close()
            self.assertFalse(is_picture_pdf(text_pdf))
            self.assertIn("rubric page", document_text(extract_pdf_text(text_pdf)))

            pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 40, 40), 1)
            pixmap.clear_with(180)
            png_path = root / "pixel.png"
            pixmap.save(png_path)
            pixmap = None
            image_pdf = root / "image.pdf"
            document = fitz.open()
            page = document.new_page()
            page.insert_image(fitz.Rect(72, 72, 200, 200), filename=str(png_path))
            document.save(image_pdf)
            document.close()
            self.assertTrue(is_picture_pdf(image_pdf))

    def test_template_docx_is_text(self) -> None:
        path = SCRIPT_DIR / "prompts" / "Template for Criterion B.docx"
        text, images = load_rubric_or_template(path)
        self.assertEqual(images, [])
        self.assertIn("Game Type", text)
        self.assertIn("Strand i", text)
        self.assertIn("Teammate", text)

    def test_rejects_image_rubric(self) -> None:
        with self.assertRaises(ValueError):
            load_rubric_or_template(SCRIPT_DIR / "prompts" / "Template for Criterion B.docx".replace(".docx", ".png"))


if __name__ == "__main__":
    unittest.main()
