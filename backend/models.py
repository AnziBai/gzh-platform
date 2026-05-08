import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from database import Base


def utcnow():
    return datetime.now(timezone.utc)


class Article(Base):
    __tablename__ = "articles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String, nullable=False)
    slug = Column(String, unique=True, nullable=False)
    file_path = Column(String)
    status = Column(String, nullable=False, default="draft")  # draft | published

    topic_id = Column(Integer, ForeignKey("topics.id"), nullable=True)
    benchmark_id = Column(Integer, ForeignKey("benchmarks.id"), nullable=True)

    structure_type = Column(String)
    word_count = Column(Integer)
    image_count = Column(Integer)

    media_id = Column(String)
    publish_timestamp = Column(DateTime)
    git_commit_hash = Column(String)

    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    stats = relationship("ArticleStat", back_populates="article", cascade="all, delete-orphan")


class ArticleStat(Base):
    __tablename__ = "article_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    article_id = Column(Integer, ForeignKey("articles.id"), nullable=False)

    read_count = Column(Integer, default=0)
    share_count = Column(Integer, default=0)
    like_count = Column(Integer, default=0)
    recommend_count = Column(Integer, default=0)
    comment_count = Column(Integer, default=0)
    underline_count = Column(Integer, default=0)
    share_rate = Column(Float)
    like_rate = Column(Float)

    fetched_at = Column(DateTime, default=utcnow)

    article = relationship("Article", back_populates="stats")


class Benchmark(Base):
    __tablename__ = "benchmarks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String, nullable=False)
    platform = Column(String, nullable=False)
    source_url = Column(String)
    file_path = Column(String)

    structure_type = Column(String)
    keywords = Column(Text)  # JSON array
    relevance_score = Column(Float)

    created_at = Column(DateTime, default=utcnow)


class Topic(Base):
    __tablename__ = "topics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String, nullable=False)
    platform = Column(String, nullable=False)  # toutiao | juejin
    source_url = Column(String)

    hot_value = Column(Integer)
    relevance_score = Column(Float)
    relevance_reason = Column(String)
    status = Column(String, default="new")  # new | selected | used | dismissed

    discovered_at = Column(DateTime, default=utcnow)
    created_at = Column(DateTime, default=utcnow)


class Task(Base):
    __tablename__ = "tasks"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    type = Column(String, nullable=False)  # generate | publish | scrape | fetch_stats
    status = Column(String, default="pending")  # pending | running | completed | failed
    progress = Column(Float, default=0)
    message = Column(String)
    result = Column(Text)  # JSON
    error = Column(Text)

    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
