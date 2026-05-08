import html
import re


STAT_CLASSES = {
    "appmsg-view": "read_count",
    "appmsg-like": "like_count",
    "appmsg-share": "share_count",
    "appmsg-haokan": "recommend_count",
    "appmsg-comment": "comment_count",
    "appmsg-underline": "underline_count",
}


def _strip_tags(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text or "")
    return html.unescape(text).strip()


def _to_int(text: str) -> int:
    match = re.search(r"\d[\d,]*", text or "")
    if not match:
        return 0
    return int(match.group(0).replace(",", ""))


def parse_publish_records_html(source: str) -> list[dict]:
    """Parse WeChat publish-record cards by semantic CSS classes, not number position."""
    records = []
    marker = '<div class="weui-desktop-mass-media weui-desktop-mass-appmsg">'
    for card in (source or "").split(marker)[1:]:
        title_match = re.search(
            r'class="weui-desktop-mass-appmsg__title"[^>]*>(?P<title>.*?)</a>',
            card,
            flags=re.S,
        )
        title = _strip_tags(title_match.group("title")) if title_match else ""
        title = re.sub(r"(?:\s*(?:付费|原创|已修改|转载|定时发表|发表成功)\s*)+$", "", title).strip()
        if not title:
            continue

        item = {
            "title": title,
            "read_count": 0,
            "share_count": 0,
            "like_count": 0,
            "recommend_count": 0,
            "comment_count": 0,
            "underline_count": 0,
        }
        for class_name, field in STAT_CLASSES.items():
            stat_match = re.search(
                rf'class="[^"]*\b{class_name}\b[^"]*"[^>]*>(?P<body>.*?)</(?:div|span|a)>',
                card,
                flags=re.S,
            )
            if stat_match:
                item[field] = _to_int(_strip_tags(stat_match.group("body")))
        records.append(item)

    return records
