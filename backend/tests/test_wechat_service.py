import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from services import wechat_service


class WechatServiceTest(unittest.TestCase):
    def test_fetch_real_stats_merges_title_variants(self):
        day_items = [
            {
                "title": "  Same Article  ",
                "int_page_read_count": 100,
                "share_count": 4,
                "add_to_fav_count": 2,
                "ori_page_read_count": 1,
            },
            {
                "title": "Same   Article",
                "int_page_read_count": 35,
                "share_count": 3,
                "add_to_fav_count": 1,
                "ori_page_read_count": 0,
            },
        ]

        with (
            patch("services.wechat_service.get_access_token", return_value="token"),
            patch(
                "services.wechat_service.get_article_summary_by_date",
                return_value=day_items,
            ),
        ):
            stats = wechat_service.fetch_real_stats(days_back=1)

        self.assertEqual(list(stats.keys()), ["Same Article"])
        self.assertEqual(stats["Same Article"]["int_page_read_count"], 135)
        self.assertEqual(stats["Same Article"]["share_count"], 7)
        self.assertEqual(stats["Same Article"]["add_to_fav_count"], 3)
        self.assertEqual(stats["Same Article"]["ori_page_read_count"], 1)


if __name__ == "__main__":
    unittest.main()
