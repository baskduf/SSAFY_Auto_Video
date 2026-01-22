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

        self.system_prompt = """당신은 실시간 강의 보조 AI입니다.
강의 내용을 분석하여 학습자에게 도움이 되는 즉각적인 피드백을 제공합니다.

역할:
1. 어려운 용어나 개념에 대한 간단한 정의 제공
2. 핵심 포인트 요약
3. 보충 설명이 필요한 부분 추가 설명
4. 관련 개념이나 예시 제시

규칙:
- 응답은 반드시 한국어로 작성
- 간결하고 명확하게 2-3문장으로 답변
- 강의 흐름을 방해하지 않도록 핵심만 전달
- 학습자가 이해하기 쉬운 표현 사용
- 불필요한 서론이나 인사말 제외"""

    async def generate_feedback(self, context: str) -> Optional[str]:
        """
        강의 맥락을 기반으로 피드백 생성
        """
        if not GEMINI_AVAILABLE:
            return self._fallback_response(context)

        if not self.api_key or not self.model:
            return self._fallback_response(context)

        try:
            prompt = f"""{self.system_prompt}

현재 강의 내용:
\"\"\"{context}\"\"\"

위 내용을 바탕으로 학습자에게 도움이 될 보충 설명, 용어 정의, 또는 핵심 요약을 제공하세요."""

            # Run in thread pool to avoid blocking
            response = await asyncio.to_thread(
                self.model.generate_content,
                prompt,
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=300,
                    temperature=0.7
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
            prompt = f"""다음 강의 내용을 핵심 포인트 위주로 요약해주세요.

강의 내용:
\"\"\"{full_transcript}\"\"\"

요약 형식:
- 주요 주제:
- 핵심 개념:
- 중요 포인트:"""

            response = await asyncio.to_thread(
                self.model.generate_content,
                prompt,
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=500,
                    temperature=0.5
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
