import asyncio
from typing import Optional
from django.conf import settings

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False


class LLMService:
    """
    Google Gemini API를 사용한 AI 피드백 생성 서비스
    """

    def __init__(self):
        self.api_key = settings.GOOGLE_API_KEY
        self.model = None

        if GEMINI_AVAILABLE and self.api_key:
            genai.configure(api_key=self.api_key)
            # Use gemini-2.0-flash or gemini-1.5-flash-latest
                # 기존
# 추천 (속도/비용 최적화)
            self.model = genai.GenerativeModel('gemini-2.5-flash-lite')

        # 추가 학습 정보 제공 프롬프트
        self.system_prompt = """당신은 실시간 강의 학습 보조 AI입니다.
강사가 설명하는 개념에 대해 **추가 학습 정보**를 제공합니다.

역할:
- 언급된 기술/개념의 관련 함수, 메서드, 사용법 추가 설명
- 실용적인 코드 예시 제공 (마크다운 코드블록 사용)
- 관련된 심화 개념이나 팁 제공

예시: 강사가 "AJAX"를 설명하면 → fetch API, axios 사용법, async/await 패턴 등 추가 정보 제공

응답 형식:
- 한국어로 간결하게 (3-4문장)
- 코드가 있으면 ```언어 코드블록 사용
- 요약하지 말고, 학습자가 더 알면 좋을 정보만 제공"""

    async def generate_feedback(self, context: str, cache_context: dict = None) -> Optional[str]:
        """
        캐시된 맥락을 활용한 실시간 추가 학습 정보 생성
        """
        if not GEMINI_AVAILABLE:
            return self._fallback_response(context)

        if not self.api_key or not self.model:
            return self._fallback_response(context)

        try:
            # 캐시에서 맥락 정보 추출
            context_hints = []
            if cache_context:
                # 주요 주제 (빈도순)
                topics = cache_context.get('top_topics', [])
                if topics:
                    topic_str = ', '.join([f"{t[0]}" for t in topics[:5]])
                    context_hints.append(f"지금까지 주요 주제: {topic_str}")

                # 이전 피드백 (중복 방지)
                last_feedback = cache_context.get('last_feedback')
                if last_feedback:
                    context_hints.append(f"이전 피드백 요약: {last_feedback[:80]}...")

            context_info = "\n".join(context_hints) if context_hints else ""

            prompt = f"""{self.system_prompt}

{context_info}

[현재 강의 내용]
{context[:500]}

추가 학습 정보 (이전 피드백과 중복되지 않게):"""

            # Run in thread pool to avoid blocking
            response = await asyncio.to_thread(
                self.model.generate_content,
                prompt,
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=300,  # 코드 예시 포함을 위해 증가
                    temperature=0.7  # 다양한 정보 제공
                )
            )

            if response and response.text:
                return response.text.strip()

            return None

        except Exception as e:
            print(f'LLM 피드백 생성 오류: {str(e)}')
            return self._fallback_response(context)

    async def generate_summary(self, full_transcript: str) -> Optional[str]:
        """
        전체 트랜스크립트 요약 생성
        """
        if not GEMINI_AVAILABLE or not self.api_key or not self.model:
            return None

        try:
            # 토큰 절약: 최대 2000자까지만 사용
            transcript_trimmed = full_transcript[:2000]
            prompt = f"""강의 요약 (한국어, 간결하게):
{transcript_trimmed}

- 주제:
- 핵심:
- 포인트:"""

            response = await asyncio.to_thread(
                self.model.generate_content,
                prompt,
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=300,  # 토큰 절약: 500 → 300
                    temperature=0.3
                )
            )

            if response and response.text:
                return response.text.strip()

            return None

        except Exception as e:
            print(f'요약 생성 오류: {str(e)}')
            return None

    async def analyze_keywords(self, context: str) -> list:
        """
        중요 키워드 추출 및 분석
        """
        if not GEMINI_AVAILABLE or not self.api_key or not self.model:
            return []

        try:
            prompt = f"""다음 강의 내용에서 중요한 키워드 5개를 추출하고 각각 간단히 설명해주세요.

강의 내용:
\"\"\"{context}\"\"\"

JSON 형식으로 응답:
[{{"keyword": "키워드", "explanation": "설명"}}]"""

            response = await asyncio.to_thread(
                self.model.generate_content,
                prompt,
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=400,
                    temperature=0.3
                )
            )

            if response and response.text:
                import json
                try:
                    # Clean up response and parse JSON
                    text = response.text.strip()
                    if text.startswith('```'):
                        text = text.split('```')[1]
                        if text.startswith('json'):
                            text = text[4:]
                    return json.loads(text)
                except json.JSONDecodeError:
                    return []

            return []

        except Exception as e:
            print(f'키워드 분석 오류: {str(e)}')
            return []

    def _fallback_response(self, context: str) -> str:
        """
        API 사용 불가 시 기본 응답
        """
        words = context.split()
        word_count = len(words)

        if word_count < 10:
            return "강의 내용을 분석 중입니다. 잠시 후 피드백이 제공됩니다."

        # Extract potential keywords (simple heuristic)
        return f"현재까지 약 {word_count}개의 단어가 감지되었습니다. AI 피드백을 위해 API 키를 설정해주세요."


class OpenAILLMService:
    """
    OpenAI GPT API를 사용한 대안 서비스
    """

    def __init__(self):
        self.api_key = settings.OPENAI_API_KEY

        if self.api_key:
            try:
                import openai
                self.client = openai.AsyncOpenAI(api_key=self.api_key)
                self.available = True
            except ImportError:
                self.available = False
        else:
            self.available = False

        self.system_prompt = """당신은 실시간 강의 보조 AI입니다.
강의 내용을 분석하여 학습자에게 도움이 되는 즉각적인 피드백을 제공합니다.
응답은 반드시 한국어로 2-3문장으로 간결하게 작성하세요."""

    async def generate_feedback(self, context: str) -> Optional[str]:
        """
        GPT를 사용한 피드백 생성
        """
        if not self.available:
            return None

        try:
            response = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": f"현재 강의 내용:\n{context}\n\n보충 설명이나 핵심 요약을 제공해주세요."}
                ],
                max_tokens=300,
                temperature=0.7
            )

            return response.choices[0].message.content.strip()

        except Exception as e:
            print(f'OpenAI 피드백 생성 오류: {str(e)}')
            return None
