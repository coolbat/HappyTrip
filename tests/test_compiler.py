import tempfile
import unittest
from pathlib import Path
from happytrip_runtime.compiler import compile_prompt
from happytrip_runtime.types import HappyTripError


class CompilerTests(unittest.TestCase):
    def test_all_eighteen_real_cards_compile(self):
        from happytrip_runtime.catalog import load_catalog, get_mode
        catalog = load_catalog()
        for item in catalog["modes"]:
            with self.subTest(mode=item["id"]):
                context = {"input_summary": "已注册的 p1", "target_summary": "用户指定目标",
                           "layout_summary": item["default_ratio"]}
                result = compile_prompt(get_mode(catalog, item["id"]), context)
                self.assertGreater(len(result), 80)
                self.assertNotIn("{{", result)

    def compile(self, body, extra=None):
        with tempfile.TemporaryDirectory() as tmp:
            card = Path(tmp) / "card.md"
            card.write_text("```text\n" + body + "\n```", encoding="utf-8")
            return compile_prompt({"id": "A05", "template_path": str(card)},
                                  {"input_summary": "p1", "layout_summary": "3:2", **(extra or {})})

    def test_optional_sentence_does_not_erase_boundary(self):
        result = self.compile("保留原片。文字：{{text_summary}}。不画日期。\n事实：{{facts_summary}}")
        self.assertIn("保留原片", result)
        self.assertIn("不画日期", result)
        self.assertNotIn("事实：", result)

    def test_placeholder_in_user_data_rejected(self):
        with self.assertRaises(HappyTripError):
            self.compile("附加：{{extra_notes}}", {"extra_notes": "{{secret}}"})

    def test_no_unresolved_variables(self):
        result = self.compile("素材 {{input_summary}}\n版式 {{layout_summary}}")
        self.assertNotIn("{{", result)
        self.assertIn("p1", result)
