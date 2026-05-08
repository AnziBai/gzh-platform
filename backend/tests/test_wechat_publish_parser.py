import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from services.wechat_publish_parser import parse_publish_records_html


class WeChatPublishParserTest(unittest.TestCase):
    def test_parse_publish_record_stats_by_semantic_class(self):
        html = """
        <div class="weui-desktop-mass-media weui-desktop-mass-appmsg">
          <a class="weui-desktop-mass-appmsg__title"><span>测试文章</span><b>付费</b><b>原创</b></a>
          <div class="weui-desktop-mass-media__data-list">
            <div class="weui-desktop-mass-media__data appmsg-view"><span>8</span></div>
            <div class="weui-desktop-mass-media__data appmsg-like"><span>1</span></div>
            <div class="weui-desktop-mass-media__data appmsg-share"><span>4</span></div>
            <div class="weui-desktop-mass-media__data appmsg-haokan"><span>2</span></div>
            <span class="weui-desktop-mass-media__data appmsg-comment"><span>3</span></span>
            <a class="weui-desktop-mass-media__data appmsg-underline"><span>5</span></a>
          </div>
        </div>
        """

        rows = parse_publish_records_html(html)

        self.assertEqual(rows, [{
            "title": "测试文章",
            "read_count": 8,
            "share_count": 4,
            "like_count": 1,
            "recommend_count": 2,
            "comment_count": 3,
            "underline_count": 5,
        }])


if __name__ == "__main__":
    unittest.main()
