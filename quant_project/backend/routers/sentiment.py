"""
감성 분석 엔드포인트 — P6 실제 RSS + VADER + Reddit 연결
캐시 우선 반환 / refresh=true 시 즉시 재수집
"""

import logging

from fastapi import APIRouter, BackgroundTasks, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()


class NewsItem(BaseModel):
    title:     str
    source:    str
    published: str
    url:       str
    sentiment: float
    ticker:    str | None = None


class SentimentSummary(BaseModel):
    as_of:         str
    overall_score: float
    n_articles:    int
    top_positive:  list[NewsItem]
    top_negative:  list[NewsItem]
    keywords:      list[str] = []


@router.get("/feed", response_model=list[NewsItem])
def get_sentiment_feed(
    ticker:  str | None = Query(None, description="종목 필터 (없으면 전체)"),
    limit:   int        = Query(20,   description="반환 건수"),
    refresh: bool       = Query(False, description="강제 재수집"),
):
    """뉴스 감성 피드 반환"""
    from services.sentiment_service import collect_sentiment, load_cached_sentiment

    if refresh:
        data = collect_sentiment()
    else:
        data = load_cached_sentiment()
        if data is None:
            data = collect_sentiment()

    items = data.get("items", [])
    if ticker:
        items = [it for it in items if it.get("ticker") == ticker.upper()]

    return [NewsItem(**it) for it in items[:limit]]


@router.get("/summary", response_model=SentimentSummary)
def get_sentiment_summary(refresh: bool = Query(False)):
    """전체 시장 감성 요약"""
    from services.sentiment_service import collect_sentiment, load_cached_sentiment

    if refresh:
        data = collect_sentiment()
    else:
        data = load_cached_sentiment()
        if data is None:
            data = collect_sentiment()

    items = data.get("items", [])
    sorted_items = sorted(items, key=lambda x: x.get("sentiment", 0))
    top_negative = [NewsItem(**it) for it in sorted_items[:5]]
    top_positive = [NewsItem(**it) for it in sorted_items[-5:][::-1]]

    return SentimentSummary(
        as_of=data.get("as_of", ""),
        overall_score=data.get("overall_score", 0.0),
        n_articles=data.get("n_articles", 0),
        top_positive=top_positive,
        top_negative=top_negative,
        keywords=data.get("keywords", []),
    )


@router.get("/reddit")
def get_reddit_sentiment(
    subreddit: str = Query("investing", description="서브레딧 이름"),
    refresh:   bool = Query(False),
):
    """Reddit 감성 — r/{subreddit} 핫 포스트"""
    from services.sentiment_service import _fetch_reddit
    items = _fetch_reddit(subreddit=subreddit)
    if not items:
        return {"subreddit": subreddit, "score": 0.0, "posts": []}
    score = sum(it["sentiment"] for it in items) / len(items)
    return {
        "subreddit": subreddit,
        "score":     round(score, 4),
        "posts":     [NewsItem(**it) for it in items[:20]],
    }


@router.post("/refresh")
def trigger_refresh(background_tasks: BackgroundTasks):
    """백그라운드로 감성 재수집 트리거"""
    from services.sentiment_service import collect_sentiment
    background_tasks.add_task(collect_sentiment)
    return {"message": "감성 분석 재수집 시작 (백그라운드)"}
