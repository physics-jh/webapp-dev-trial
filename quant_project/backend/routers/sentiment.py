"""
P3 뼈대 / P6에서 RSS + VADER + Reddit 연결
감성 분석 엔드포인트
"""

from fastapi import APIRouter, Query
from pydantic import BaseModel

router = APIRouter()


class NewsItem(BaseModel):
    title:      str
    source:     str
    published:  str
    url:        str
    sentiment:  float   # VADER compound: -1 ~ +1
    ticker:     str | None = None


class SentimentSummary(BaseModel):
    as_of:          str
    overall_score:  float
    n_articles:     int
    top_positive:   list[NewsItem]
    top_negative:   list[NewsItem]


@router.get("/feed", response_model=list[NewsItem])
def get_sentiment_feed(
    ticker: str | None = Query(None, description="특정 종목 필터 (없으면 전체)"),
    limit:  int        = Query(20,   description="반환 건수"),
):
    """뉴스 감성 피드 — P6에서 RSS + VADER 연결"""
    # TODO(P6): feedparser + VADER 연결
    return []


@router.get("/summary", response_model=SentimentSummary)
def get_sentiment_summary():
    """전체 시장 감성 요약 — P6에서 APScheduler 갱신 결과 연결"""
    # TODO(P6)
    return SentimentSummary(
        as_of="", overall_score=0.0, n_articles=0,
        top_positive=[], top_negative=[],
    )


@router.get("/reddit")
def get_reddit_sentiment(subreddit: str = Query("investing")):
    """Reddit 감성 — P6에서 PRAW 연결"""
    # TODO(P6)
    return {"subreddit": subreddit, "score": 0.0, "posts": []}
