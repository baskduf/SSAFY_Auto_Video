import json
import asyncio
import time
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings
from .services.audio_processor import AudioProcessor
from .services.stt_service import SimplifiedSTTService
from .services.llm_service import LLMService
from .services.context_cache import ContextCache


class StreamConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.audio_processor = None
        self.stt_service = None
        self.llm_service = None
        self.context_cache = None  # 컨텍스트 캐시
        self.is_streaming = False
        self.transcript_buffer = []
        self.last_feedback_time = 0
        self.feedback_interval = 20  # API 제한 고려 (분당 10회 = 6초마다 가능하지만 여유있게)
        self.min_words_for_feedback = 30  # 의미있는 컨텐츠 확보
        self.start_time = 0

    async def connect(self):
        await self.accept()
        self.stt_service = SimplifiedSTTService()
        self.llm_service = LLMService()
        self.context_cache = ContextCache(max_history=50)
        await self.send(text_data=json.dumps({
            'type': 'connection',
            'status': 'connected',
            'message': 'WebSocket 연결 성공'
        }))

    async def disconnect(self, close_code):
        self.is_streaming = False
        if self.audio_processor:
            await self.audio_processor.stop()
        if self.stt_service:
            await self.stt_service.close()

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            action = data.get('action')

            if action == 'start':
                youtube_url = data.get('url')
                if youtube_url:
                    await self.start_streaming(youtube_url)
            elif action == 'stop':
                await self.stop_streaming()
        except json.JSONDecodeError:
            await self.send_error('잘못된 메시지 형식입니다.')

    async def start_streaming(self, youtube_url):
        if self.is_streaming:
            await self.send_error('이미 스트리밍 중입니다.')
            return

        self.is_streaming = True
        self.transcript_buffer = []
        self.context_cache.reset()  # 캐시 초기화
        self.start_time = time.time()
        self.last_feedback_time = self.start_time

        await self.send_status('starting', '스트리밍 시작 중...')

        try:
            self.audio_processor = AudioProcessor(youtube_url)
            # Start audio processing in background task
            asyncio.create_task(self.process_audio_stream())
        except Exception as e:
            self.is_streaming = False
            await self.send_error(f'스트리밍 시작 실패: {str(e)}')

    async def process_audio_stream(self):
        """Process audio stream and send to STT"""
        try:
            await self.send_status('extracting', '오디오 스트림 추출 중...')

            # 2초 청크 + 20% 오버랩으로 음성 누락 방지
            async for audio_chunk in self.audio_processor.stream_audio_chunks(chunk_duration=2.0, overlap=0.2):
                if not self.is_streaming:
                    break

                await self.send_status('streaming', '스트리밍 중...')

                # Send audio chunk to STT
                transcript = await self.stt_service.transcribe(audio_chunk)

                if transcript and transcript.strip():
                    self.transcript_buffer.append(transcript)

                    # 컨텍스트 캐시에 추가 및 분석
                    elapsed = time.time() - self.start_time
                    analysis = self.context_cache.add_transcript(transcript, elapsed)

                    # Send transcript to client
                    await self.send(text_data=json.dumps({
                        'type': 'transcript',
                        'text': transcript,
                        'timestamp': elapsed
                    }))

                    # 스마트 피드백 트리거 (API 제한 고려)
                    current_time = time.time()
                    time_since_last = current_time - self.last_feedback_time
                    topic_changed = analysis.get('topic_changed', False)
                    has_new_keywords = len(analysis.get('keywords', [])) >= 3

                    # 최소 10초 간격 보장 (API 레이트 리밋 보호)
                    min_interval = 10

                    # 조건 1: 기본 시간 간격 충족 (20초)
                    # 조건 2: 주제 변화 감지 (10초 이상 경과)
                    # 조건 3: 새 키워드 3개 이상 (15초 이상 경과)
                    should_trigger = (
                        time_since_last >= self.feedback_interval or
                        (topic_changed and time_since_last >= min_interval) or
                        (has_new_keywords and time_since_last >= 15)
                    )

                    if should_trigger:
                        trigger = self.context_cache.should_generate_feedback(self.min_words_for_feedback)
                        if trigger.get('should', False):
                            asyncio.create_task(self.generate_feedback())
                            self.last_feedback_time = current_time

        except asyncio.CancelledError:
            pass
        except Exception as e:
            await self.send_error(f'오디오 처리 오류: {str(e)}')
        finally:
            self.is_streaming = False
            await self.send_status('stopped', '스트리밍 종료')

    async def generate_feedback(self):
        """컨텍스트 캐시 기반 실시간 AI 피드백 생성"""
        # 캐시에서 전체 컨텍스트 가져오기
        cache_ctx = self.context_cache.get_feedback_context()
        context_text = cache_ctx.get('recent_text', '')

        if not context_text or len(context_text.split()) < self.min_words_for_feedback:
            return

        try:
            # 전체 캐시 컨텍스트를 LLM에 전달 (주제, 이전 피드백 포함)
            feedback = await self.llm_service.generate_feedback(context_text, cache_ctx)

            if feedback:
                # 캐시에 피드백 기록 (중복 방지용)
                self.context_cache.add_feedback(feedback)

                elapsed = time.time() - self.start_time
                await self.send(text_data=json.dumps({
                    'type': 'feedback',
                    'content': feedback,
                    'timestamp': elapsed
                }))
        except Exception as e:
            print(f'피드백 생성 오류: {str(e)}')

    async def stop_streaming(self):
        self.is_streaming = False
        if self.audio_processor:
            await self.audio_processor.stop()

        await self.send_status('stopped', '스트리밍이 중지되었습니다.')

    async def send_status(self, status: str, message: str):
        await self.send(text_data=json.dumps({
            'type': 'status',
            'status': status,
            'message': message
        }))

    async def send_error(self, message: str):
        await self.send(text_data=json.dumps({
            'type': 'error',
            'message': message
        }))
