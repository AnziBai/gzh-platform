import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from services.publish_service import _assert_audit_passed


class PublishServiceTest(unittest.TestCase):
    def test_assert_audit_passed_accepts_pass(self):
        _assert_audit_passed("审查结果：PASS\n\n检查项：都通过")

    def test_assert_audit_passed_rejects_fail(self):
        with self.assertRaisesRegex(RuntimeError, "审查未通过"):
            _assert_audit_passed("审查结果：FAIL\n\n必须修改的问题：\n- 缺少 title")

    def test_assert_audit_passed_rejects_ambiguous_output(self):
        with self.assertRaisesRegex(RuntimeError, "未输出明确"):
            _assert_audit_passed("整体还可以，但建议修改。")


if __name__ == "__main__":
    unittest.main()
