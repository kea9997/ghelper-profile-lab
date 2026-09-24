"""Synthetic Time Spy archives only; no private real-result fixtures."""
from pathlib import Path
import tempfile
import unittest
import warnings
import zipfile

import result_reader as reader


TAGS = (
    "TimeSpyPerformance3DMarkScore", "TimeSpyPerformanceGraphicsScore", "TimeSpyPerformanceCPUScore",
)


def result_xml(scores=(12000, 13000, 10000), namespace=""):
    prefix = "t:" if namespace else ""
    attrs = ' xmlns:t="urn:3dmark:synthetic-test"' if namespace else ""
    return "<Result" + attrs + ">" + "".join(f"<{prefix}{tag}>{score}</{prefix}{tag}>" for tag, score in zip(TAGS, scores)) + "</Result>"


class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "test.3dmark-result"

    def archive(self, xml=None, extras=()):
        with warnings.catch_warnings(), zipfile.ZipFile(self.path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            warnings.simplefilter("ignore", UserWarning)  # Duplicate names intentionally model hostile archives.
            if xml is not None:
                zf.writestr("Result.xml", xml)
            for name, data in extras:
                zf.writestr(name, data)
        return self.path

    def test_actual_timespy_score_tags_and_namespaces(self):
        for namespace in ("", "namespaced"):
            with self.subTest(namespace=namespace):
                parsed = reader.parse_result(self.archive(result_xml(namespace=namespace)))
                self.assertEqual(parsed, {"totalScore": 12000, "graphicsScore": 13000, "cpuScore": 10000,
                                          "status": "valid", "benchmark": "Time Spy", "temperatures": {}})

    def test_any_zero_component_marks_run_failed(self):
        for scores in ((0, 13000, 10000), (12000, 0, 10000), (12000, 13000, 0)):
            with self.subTest(scores=scores):
                self.assertEqual(reader.parse_result(self.archive(result_xml(scores)))["status"], "failed")

    def test_invalid_scores_are_rejected(self):
        for score in ("-1", "1000001", "NaN", "Infinity", "12.3", "", "1e4", "true"):
            with self.subTest(score=score), self.assertRaises(ValueError):
                reader.parse_result(self.archive(result_xml((score, 13000, 10000))))

    def test_missing_or_other_benchmark_tags_are_rejected(self):
        xml = result_xml().replace("TimeSpyPerformance", "TimeSpyExtreme")
        with self.assertRaises(ValueError):
            reader.parse_result(self.archive(xml))

    def test_duplicate_scores_are_rejected_even_across_namespaces(self):
        extra = f'<e:{TAGS[0]} xmlns:e="urn:other">1</e:{TAGS[0]}>'
        xml = result_xml().replace("</Result>", extra + "</Result>")
        with self.assertRaisesRegex(ValueError, "duplicate"):
            reader.parse_result(self.archive(xml))

    def test_xxe_and_doctype_rejected_in_utf8_and_utf16(self):
        xml = '<!DOCTYPE Result [<!ENTITY probe SYSTEM "file:///C:/synthetic-private-file">]>' + result_xml()
        for encoding in ("utf-8", "utf-16", "utf-16-be"):
            with self.subTest(encoding=encoding), self.assertRaises(ValueError):
                reader.parse_result(self.archive(xml.encode(encoding)))

    def test_entity_declaration_rejected_even_without_doctype(self):
        xml = '<!ENTITY probe "test">' + result_xml()
        with self.assertRaises(ValueError):
            reader.parse_result(self.archive(xml))

    def test_malformed_xml_is_a_value_error(self):
        with self.assertRaises(ValueError):
            reader.parse_result(self.archive("<Result><broken>"))

    def test_temperature_maxima_from_semicolon_monitoring(self):
        csv = ("Time;GPU Temperature (C);CPU Temperature (C)\n"
               "0;60;75\n1;80;95\n2;nan;Infinity\n3;151;-4\n4;70;90\n")
        parsed = reader.parse_result(self.archive(result_xml(), [("Monitoring.csv", csv)]))
        self.assertEqual(parsed["temperatures"], {"gpuMax": 80.0, "cpuMax": 95.0})

    def test_missing_temperature_data_is_empty_not_fake(self):
        parsed = reader.parse_result(self.archive(result_xml(), [("Monitoring.csv", "Time,GPU clock\n0,2000\n")]))
        self.assertEqual(parsed["temperatures"], {})

    def test_zip_traversal_absolute_and_drive_paths_are_rejected(self):
        for name in ("../escape.txt", "safe/../../escape.txt", "safe\\..\\escape.txt", "/absolute.txt",
                     "\\server\\share.txt", "C:\\absolute.txt", "C:relative.txt", "safe//entry", "./entry"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                reader.parse_result(self.archive(result_xml(), [(name, "payload")]))
        self.assertFalse((self.root.parent / "escape.txt").exists())

    def test_duplicate_result_xml_is_rejected(self):
        with self.assertRaises(ValueError):
            reader.parse_result(self.archive(result_xml(), [("Result.xml", result_xml())]))

    def test_duplicate_monitoring_files_are_rejected(self):
        with self.assertRaises(ValueError):
            reader.parse_result(self.archive(result_xml(), [("Monitoring.csv", ""), ("other/Monitoring.csv", "")]))

    def test_missing_or_nested_result_xml_is_rejected(self):
        for extras in ([], [("nested/Result.xml", result_xml())]):
            with self.subTest(extras=extras), self.assertRaises(ValueError):
                reader.parse_result(self.archive(extras=extras))

    def test_non_zip_and_truncated_zip_are_normalized_to_value_error(self):
        self.path.write_bytes(b"Not a zip file")
        with self.assertRaises(ValueError):
            reader.parse_result(self.path)
        self.archive(result_xml())
        self.path.write_bytes(self.path.read_bytes()[:40])
        with self.assertRaises(ValueError):
            reader.parse_result(self.path)

    def test_crc_failure_is_a_value_error(self):
        with zipfile.ZipFile(self.path, "w", compression=zipfile.ZIP_STORED) as zf:
            zf.writestr("Result.xml", result_xml())
        raw = self.path.read_bytes()
        self.assertIn(b">12000<", raw)
        self.path.write_bytes(raw.replace(b">12000<", b">12001<", 1))
        with self.assertRaises(ValueError):
            reader.parse_result(self.path)

    def test_oversized_xml_rejected_before_parsing(self):
        xml = b" " * (1024 * 1024 + 1)
        with self.assertRaisesRegex(ValueError, "size limit"):
            reader.parse_result(self.archive(xml))

    def test_compressed_bomb_total_size_limit(self):
        extras = [("unused.bin", b"0" * (32 * 1024 * 1024))]
        self.archive(result_xml(), extras)
        self.assertLess(self.path.stat().st_size, 100000)
        with self.assertRaisesRegex(ValueError, "uncompressed size"):
            reader.parse_result(self.path)

    def test_entry_count_limit(self):
        extras = [(f"item{i}.txt", "") for i in range(100)]
        with self.assertRaisesRegex(ValueError, "too many entries"):
            reader.parse_result(self.archive(result_xml(), extras))


if __name__ == "__main__":
    unittest.main()
