import copy
import unittest
from unittest.mock import patch

from main import load, raise_validation_errors, transform, validate


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.record = {
            "MOVIES": "Example", "YEAR": "(2021)", "GENRE": "Action",
            "RATING": "7.5", "VOTES": "1,234", "RunTime": "90",
            "Gross": "$1.25M", "ONE-LINE": "Synopsis",
            "STARS": "Director: Alice | Stars: Bob",
        }
        self.payload = transform([self.record])

    def test_valid_payload_and_nullable_values(self):
        validate(self.payload)
        blank = dict.fromkeys(self.record, "")
        validate(transform([blank]))

    def test_identical_titles_merge_without_losing_relations(self):
        first = dict(self.record, Gross="", YEAR="(2021– )")
        second = dict(first, GENRE="Action, Drama", STARS="Director: Alice | Stars: Alice, Bob, Carol")
        payload = transform([first, second])
        self.assertEqual(len(payload["titles"]), 1)
        self.assertEqual(payload["titles"][0]["gross"], None)
        self.assertEqual(len(payload["title_genres"]), 2)
        self.assertTrue(all(row["title_ref"] == 0 for row in payload["title_genres"] + payload["credits"]))
        credits = {
            (payload["persons"][row["person_ref"]]["person_name"], row["role"])
            for row in payload["credits"]
        }
        self.assertEqual(credits, {("Alice", "director"), ("Alice", "actor"), ("Bob", "actor"), ("Carol", "actor")})
        self.assertEqual(len(payload["credits"]), 4)

    def test_same_name_with_different_attributes_stays_separate(self):
        payload = transform([self.record, dict(self.record, RATING="5.7", **{"ONE-LINE": "Different synopsis"})])
        self.assertEqual(len(payload["titles"]), 2)
        self.assertEqual({row["title_ref"] for row in payload["credits"]}, {0, 1})

    def test_missing_source_column(self):
        del self.record["STARS"]
        with self.assertLogs("main", level="ERROR") as logs, self.assertRaises(ValueError):
            transform([self.record])
        self.assertIn("STARS", " ".join(logs.output))

    def test_invalid_number_reports_column(self):
        bad = dict(self.record, RATING="invalid")
        with self.assertLogs("main", level="ERROR") as logs, self.assertRaises(ValueError):
            transform([self.record, self.record.copy(), bad])
        self.assertIn("RATING", " ".join(logs.output))

    def test_year_formats(self):
        rows = [dict(self.record, YEAR=year) for year in ["(2021)", "(2021– )", "(2010–2022)", "(I)"]]
        payload = transform([rows[0], rows[0].copy(), *rows[1:]])
        self.assertEqual([row["release_end_year"] for row in payload["titles"]], [2021, None, 2022, None])

    def test_schema_value_errors(self):
        cases = [
            ("rating", 10.1), ("votes", -1),
            ("runtime_minutes", 0), ("gross", float("inf")),
            ("gross", -1.0), ("release_end_year", 2020),
        ]
        for column, value in cases:
            with self.subTest(column=column, value=value):
                payload = copy.deepcopy(self.payload)
                payload["titles"][0][column] = value
                with self.assertLogs("main", level="ERROR"), self.assertRaises(ValueError):
                    validate(payload)

    def test_invalid_payload_never_opens_database(self):
        self.payload["titles"][0]["runtime_minutes"] = 0
        with patch("main.create_db_engine") as engine:
            with self.assertLogs("main", level="ERROR"), self.assertRaises(ValueError):
                load(self.payload)
            engine.assert_not_called()

    def test_error_logging_is_limited_to_ten_examples(self):
        with patch("main.logger.error") as error_log, self.assertRaises(ValueError):
            raise_validation_errors([f"error {index}" for index in range(15)], "test")
        self.assertEqual(error_log.call_count, 11)  # Ringkasan + 10 contoh.


if __name__ == "__main__":
    unittest.main()
