"""
SentimentService — RSS feedparser + VADER + Reddit PRAW
SENTIMENT_SOURCE=rss_vader (기본) → newsapi_finbert (실전) 전환 가능
결과는 data/processed/sentiment_cache.json 에 저장 (APScheduler 18:30 갱신)
"""

from __future__ import annotations
import json
import logging
import os
import re
from datetime import datetime
from typing import TypedDict

logger = logging.getLogger(__name__)

# ─── 데이터 타입 ──────────────────────────────────────────────

class NewsItem(TypedDict):
    title:     str
    source:    str
    published: str
    url:       str
    sentiment: float      # VADER compound: -1 ~ +1
    ticker:    str | None


class SentimentResult(TypedDict):
    as_of:         str
    overall_score: float
    n_articles:    int
    items:         list[NewsItem]
    keywords:      list[str]   # TF-IDF top 10


CACHE_PATH = None  # 초기화 전 None, _get_cache_path() 로 지연 로드


def _get_cache_path() -> str:
    from config import DATA_PROCESSED
    return os.path.join(DATA_PROCESSED, "sentiment_cache.json")


# ─── RSS 수집 ─────────────────────────────────────────────────

RSS_FEEDS = [
    ("Yahoo Finance",  "https://finance.yahoo.com/rss/topstories"),
    ("Yahoo Finance Markets", "https://finance.yahoo.com/rss/2.0/headline?s=^GSPC&region=US&lang=en-US"),
    ("Reuters Business", "https://feeds.reuters.com/reuters/businessNews"),
]


def _fetch_rss(limit_per_feed: int = 30) -> list[NewsItem]:
    import feedparser
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    analyzer = SentimentIntensityAnalyzer()
    known = _get_known_tickers()

    items: list[NewsItem] = []
    for source_name, url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:limit_per_feed]:
                title     = entry.get("title", "")
                link      = entry.get("link", "")
                published = entry.get("published", str(datetime.utcnow()))
                score     = analyzer.polarity_scores(title)["compound"]
                ticker    = _extract_ticker(title, known)
                items.append(NewsItem(
                    title=title, source=source_name,
                    published=published, url=link,
                    sentiment=score, ticker=ticker,
                ))
        except Exception as e:
            logger.warning(f"RSS 수집 실패 ({source_name}): {e}")
    return items


def _extract_ticker(text: str, known_tickers: set[str] | None = None) -> str | None:
    """텍스트에서 $TICKER 패턴 또는 알려진 티커 심볼 추출

    1순위: $TICKER 달러 패턴 (e.g. $AAPL)
    2순위: known_tickers 집합에 있는 대문자 단어 (e.g. "AAPL stock rises")
    """
    # 1순위: $TICKER
    match = re.search(r'\$([A-Z]{1,5})\b', text)
    if match:
        return match.group(1)
    # 2순위: 알려진 티커 집합과 매칭
    if known_tickers:
        for word in re.findall(r'\b([A-Z]{1,5})\b', text):
            if word in known_tickers:
                return word
    return None


def _get_known_tickers() -> set[str]:
    """factors.parquet 에서 알려진 티커 집합 로드 (캐시)"""
    try:
        from config import DATA_PROCESSED
        import pandas as pd
        fp = os.path.join(DATA_PROCESSED, "factors.parquet")
        if os.path.exists(fp):
            df = pd.read_parquet(fp)
            if "ticker" in df.columns:
                return set(df["ticker"].unique())
    except Exception:
        pass
    return set()


# ─── Reddit 수집 ──────────────────────────────────────────────

def _fetch_reddit(subreddit: str = "investing", limit: int = 50) -> list[NewsItem]:
    from config import REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET
    if not REDDIT_CLIENT_ID or not REDDIT_CLIENT_SECRET:
        logger.info("Reddit API 키 미설정 — 건너뜀")
        return []
    try:
        import praw
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        analyzer = SentimentIntensityAnalyzer()

        reddit = praw.Reddit(
            client_id=REDDIT_CLIENT_ID,
            client_secret=REDDIT_CLIENT_SECRET,
            user_agent="QuantVision/1.0",
        )
        sub    = reddit.subreddit(subreddit)
        known  = _get_known_tickers()
        items: list[NewsItem] = []
        for post in sub.hot(limit=limit):
            title = post.title
            score = analyzer.polarity_scores(title)["compound"]
            ticker = _extract_ticker(title, known)
            items.append(NewsItem(
                title=title, source=f"r/{subreddit}",
                published=str(datetime.utcfromtimestamp(post.created_utc)),
                url=f"https://reddit.com{post.permalink}",
                sentiment=score, ticker=ticker,
            ))
        return items
    except Exception as e:
        logger.warning(f"Reddit 수집 실패: {e}")
        return []


# ─── TF-IDF 키워드 ────────────────────────────────────────────

def _top_keywords(items: list[NewsItem], top_n: int = 10) -> list[str]:
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        texts = [it["title"] for it in items if it["title"]]
        if not texts:
            return []
        vec = TfidfVectorizer(stop_words="english", max_features=200)
        vec.fit(texts)
        scores = vec.idf_
        terms  = vec.get_feature_names_out()
        top    = sorted(zip(terms, scores), key=lambda x: -x[1])[:top_n]
        return [t for t, _ in top]
    except Exception as e:
        logger.warning(f"TF-IDF 실패: {e}")
        return []


# ─── 메인 수집 함수 ───────────────────────────────────────────

def collect_sentiment(subreddits: list[str] | None = None) -> SentimentResult:
    """RSS + Reddit 수집 → VADER 감성 분석 → 결과 반환 및 캐시 저장"""
    all_items: list[NewsItem] = []
    all_items += _fetch_rss()
    for sub in (subreddits or ["investing", "stocks"]):
        all_items += _fetch_reddit(sub)

    if not all_items:
        result = SentimentResult(
            as_of=datetime.utcnow().isoformat(),
            overall_score=0.0, n_articles=0,
            items=[], keywords=[],
        )
    else:
        overall = sum(it["sentiment"] for it in all_items) / len(all_items)
        keywords = _top_keywords(all_items)
        result = SentimentResult(
            as_of=datetime.utcnow().isoformat(),
            overall_score=round(overall, 4),
            n_articles=len(all_items),
            items=all_items,
            keywords=keywords,
        )

    # 캐시 저장
    try:
        path = _get_cache_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"감성 캐시 저장 실패: {e}")

    return result


def load_cached_sentiment() -> SentimentResult | None:
    """캐시된 감성 분석 결과 로드"""
    path = _get_cache_path()
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)
