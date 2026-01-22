"""
실시간 강의 컨텍스트 캐시 서비스
- 주제/키워드 추적
- 맥락 연결성 유지
- 중복 피드백 방지
"""

import time
from collections import deque
from typing import List, Dict, Optional
import re


class ContextCache:
    """강의 내용의 맥락을 추적하고 연결성 있는 피드백을 위한 캐시"""

    def __init__(self, max_history: int = 50):
        # 최근 트랜스크립트 (슬라이딩 윈도우)
        self.transcripts = deque(maxlen=max_history)

        # 감지된 주제/키워드
        self.topics: Dict[str, int] = {}  # {keyword: count}

        # 이전 피드백 (중복 방지용)
        self.previous_feedbacks: List[str] = []

        # 주제 변화 감지
        self.last_topic_keywords: set = set()

        # 통계
        self.total_words = 0
        self.session_start = time.time()

        # 한국어 불용어 (피드백에서 제외할 단어)
        self.stopwords = {
            '그리고', '그러나', '하지만', '그래서', '따라서', '이것', '저것',
            '여기', '거기', '이런', '저런', '어떤', '무엇', '누구', '언제',
            '어디', '어떻게', '왜', '그냥', '정말', '매우', '아주', '너무',
            '있습니다', '없습니다', '합니다', '됩니다', '입니다', '것입니다'
        }

    def add_transcript(self, text: str, timestamp: float) -> Dict:
        """새 트랜스크립트 추가 및 분석"""
        self.transcripts.append({
            'text': text,
            'timestamp': timestamp,
            'added_at': time.time()
        })

        # 단어 수 업데이트
        words = text.split()
        self.total_words += len(words)

        # 키워드 추출 및 주제 업데이트
        keywords = self._extract_keywords(text)
        for kw in keywords:
            self.topics[kw] = self.topics.get(kw, 0) + 1

        # 주제 변화 감지
        current_keywords = set(keywords)
        topic_changed = self._detect_topic_change(current_keywords)
        self.last_topic_keywords = current_keywords

        return {
            'keywords': keywords,
            'topic_changed': topic_changed,
            'total_words': self.total_words
        }

    def _extract_keywords(self, text: str) -> List[str]:
        """간단한 키워드 추출 (명사 위주)"""
        # 특수문자 제거 및 단어 분리
        words = re.findall(r'[가-힣a-zA-Z0-9]+', text)

        keywords = []
        for word in words:
            # 2글자 이상, 불용어 아닌 것
            if len(word) >= 2 and word not in self.stopwords:
                # 영어는 소문자로
                if word.isascii():
                    word = word.lower()
                keywords.append(word)

        return keywords

    def _detect_topic_change(self, current_keywords: set) -> bool:
        """주제 변화 감지 (새 키워드 비율로 판단)"""
        if not self.last_topic_keywords:
            return False

        # 새로운 키워드 비율
        new_keywords = current_keywords - self.last_topic_keywords
        if len(current_keywords) == 0:
            return False

        new_ratio = len(new_keywords) / len(current_keywords)
        return new_ratio > 0.6  # 60% 이상 새 키워드면 주제 변화

    def get_context_summary(self, num_recent: int = 10) -> str:
        """최근 컨텍스트 요약"""
        recent = list(self.transcripts)[-num_recent:]
        return ' '.join([t['text'] for t in recent])

    def get_top_topics(self, n: int = 5) -> List[tuple]:
        """상위 n개 주제/키워드"""
        sorted_topics = sorted(self.topics.items(), key=lambda x: x[1], reverse=True)
        return sorted_topics[:n]

    def should_generate_feedback(self, min_words: int = 20) -> Dict:
        """피드백 생성 여부 결정 (더 적극적인 실시간 트리거)"""
        recent = list(self.transcripts)[-3:]  # 더 적은 트랜스크립트로 빠른 반응
        if not recent:
            return {'should': False, 'reason': 'no_content'}

        recent_text = ' '.join([t['text'] for t in recent])
        word_count = len(recent_text.split())

        # 조건 1: 최소 단어 수 (완화됨)
        if word_count < min_words:
            return {'should': False, 'reason': 'insufficient_words'}

        # 조건 2: 주제 변화 감지
        current_keywords = set(self._extract_keywords(recent_text))
        topic_changed = self._detect_topic_change(current_keywords)

        # 조건 3: 새로운 주요 키워드 등장
        top_topics = set([t[0] for t in self.get_top_topics(3)])
        has_key_topic = bool(current_keywords & top_topics)

        # 새로운 키워드가 있으면 무조건 피드백
        new_keywords = current_keywords - self.last_topic_keywords
        has_new_content = len(new_keywords) >= 2

        return {
            'should': True,
            'reason': 'topic_change' if topic_changed else ('new_content' if has_new_content else 'regular'),
            'topic_changed': topic_changed,
            'has_key_topic': has_key_topic,
            'has_new_content': has_new_content,
            'word_count': word_count
        }

    def add_feedback(self, feedback: str):
        """생성된 피드백 기록 (중복 방지용)"""
        self.previous_feedbacks.append(feedback)
        # 최근 10개만 유지
        if len(self.previous_feedbacks) > 10:
            self.previous_feedbacks = self.previous_feedbacks[-10:]

    def get_feedback_context(self) -> Dict:
        """피드백 생성을 위한 풍부한 컨텍스트 정보"""
        # 최근 텍스트 (더 많이 가져오기)
        recent_text = self.get_context_summary(15)

        # 최근 새로 등장한 키워드 (마지막 5개 트랜스크립트에서)
        recent_transcripts = list(self.transcripts)[-5:]
        recent_keywords = set()
        for t in recent_transcripts:
            recent_keywords.update(self._extract_keywords(t['text']))

        return {
            'recent_text': recent_text,
            'top_topics': self.get_top_topics(5),
            'recent_keywords': list(recent_keywords)[:10],
            'total_words': self.total_words,
            'duration': time.time() - self.session_start,
            'previous_feedback_count': len(self.previous_feedbacks),
            'last_feedback': self.previous_feedbacks[-1] if self.previous_feedbacks else None
        }

    def get_running_summary(self) -> str:
        """현재까지의 러닝 서머리"""
        top_topics = self.get_top_topics(5)
        if not top_topics:
            return ""

        topic_str = ', '.join([f"{t[0]}({t[1]}회)" for t in top_topics])
        return f"주요 주제: {topic_str}"

    def reset(self):
        """캐시 초기화"""
        self.transcripts.clear()
        self.topics.clear()
        self.previous_feedbacks.clear()
        self.last_topic_keywords.clear()
        self.total_words = 0
        self.session_start = time.time()
