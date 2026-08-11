import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("patcher", ROOT / "patcher.py")
patcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patcher)


class PatcherTests(unittest.TestCase):
    def test_translation_count_and_ids(self):
        entries = patcher.load_translations()
        self.assertEqual(len(entries), 18)
        self.assertEqual(entries[0]["id"], 77010001)
        self.assertEqual(entries[-1]["id"], 77010018)
        self.assertEqual(len({e["key"] for e in entries}), 18)

    def test_fnv1_known_vector(self):
        # 固定向量，防止无意修改 SDS Safe hash 算法。
        self.assertEqual(patcher.fnv1(b"SDS\x00\x13\x00\x00\x00PC\x00\x00"), 0x5FFB74F3)

    def test_content_patch_is_idempotent(self):
        sample = """\ufeff<xml>\r\n\t<Mount TriggerId=\"GameLine_3_English\">\r\n\t\t<Src>/sds_en</Src>\r\n\t\t<Dst>/sds</Dst>\r\n\t\t<Files>\r\n\t\t\t<File Name=\"/gui/gui-main_dlc_zfl.sds\" />\r\n\t\t</Files>\r\n\t</Mount>\r\n\t<Mount TriggerId=\"English\">\r\n\t\t<Src>/sds_en/gui</Src>\r\n\t\t<Dst>/sds/gui</Dst>\r\n\t\t<Files>\r\n\t\t\t<File Name=\"/gui-main_dlc_zfl.sds\" />\r\n\t\t</Files>\r\n\t</Mount>\r\n\t<Content Name=\"Friends for Life\" Type=\"MISSION_PACK\">\r\n\t\t<Params>\r\n\t\t\t<Param Name=\"GuiSDS\">/sds/gui/gui-main_dlc_zfl</Param>\r\n\t\t</Params>\r\n\t</Content>\r\n</xml>\r\n"""
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "content"
            p.write_text(sample, encoding="utf-8-sig", newline="")
            patcher.patch_content(p)
            once = p.read_bytes()
            patcher.patch_content(p)
            twice = p.read_bytes()
            self.assertEqual(once, twice)
            txt = once.decode("utf-8-sig")
            self.assertEqual(txt.count('TriggerId="GameLine_3_Chinesesimp"'), 1)
            self.assertEqual(txt.count('TriggerId="Chinesesimp"'), 1)
            self.assertEqual(txt.count('MainMenuTdbFile'), 1)


if __name__ == "__main__":
    unittest.main()
