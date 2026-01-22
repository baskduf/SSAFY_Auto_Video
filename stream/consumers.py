import json
import asyncio
import time
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings
from .services.audio_processor import AudioProcessor
from .services.stt_service import SimplifiedSTTService
from .services.llm_service import LLMService


class StreamConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.audio_processor = None
        self.stt_service = None
        self.llm_service = None
        self.is_streaming = False
        self.transcript_buffer = []
        self.context_window = []
        self.last_feedback_time = 0
        self.feedback_interval = 25  # seconds
        self.start_time = 0

    async def connect(self):
        await self.accept()
        self.stt_service = SimplifiedSTTService()
        self.llm_service = LLMService()
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
        self.context_window = []
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

            # Use chunk-based streaming (3 seconds per chunk)
            async for audio_chunk in self.audio_processor.stream_audio_chunks(chunk_duration=3.0):
                if not self.is_streaming:
                    break

                await self.send_status('streaming', '스트리밍 중...')

                # Send audio chunk to STT
                transcript = await self.stt_service.transcribe(audio_chunk)

                if transcript and transcript.strip():
                    self.transcript_buffer.append(transcript)
                    self.context_window.append(transcript)

                    # Keep context window manageable (last ~5 minutes)
                    if len(self.context_window) > 100:
                        self.context_window = self.context_window[-80:]

                    # Send transcript to client
                    elapsed = time.time() - self.start_time
                    await self.send(text_data=json.dumps({
                        'type': 'transcript',
                        'text': transcript,
                        'timestamp': elapsed
                    }))

                    # Check if we should generate feedback
                    current_time = time.time()
                    if current_time - self.last_feedback_time >= self.feedback_interval:
                        asyncio.create_task(self.generate_feedback())
                        self.last_feedback_time = current_time

        except asyncio.CancelledError:
            pass
        except Exception as e:
            await self.send_error(f'오디오 처리 오류: {str(e)}')
        finally:
            self.is_streaming = False
            await self.send_status('stopped', '스트리밍 종료')

            # Generate final summary if we have content
            if len(self.transcript_buffer) > 5:
                await self.generate_summary()

    async def generate_feedback(self):
        """Generate AI feedback based on context"""
        if not self.context_window or len(self.context_window) < 3:
            return

        # Use recent context (last ~60 seconds)
        recent_context = self.context_window[-20:]
        context_text = ' '.join(recent_context)

        if len(context_text) < 50:
            return

        try:
            feedback = await self.llm_service.generate_feedback(context_text)

            if feedback:
                elapsed = time.time() - self.start_time
                await self.send(text_data=json.dumps({
                    'type': 'feedback',
                    'content': feedback,
                    'timestamp': elapsed
                }))
        except Exception as e:
            print(f'피드백 생성 오류: {str(e)}')

    async def generate_summary(self):
        """Generate summary when stream ends"""
        if not self.transcript_buffer:
            return

        full_transcript = ' '.join(self.transcript_buffer)

        try:
            summary = await self.llm_service.generate_summary(full_transcript)

            if summary:
                await self.send(text_data=json.dumps({
                    'type': 'summary',
                    'content': summary,
                    'timestamp': time.time() - self.start_time
                }))
        except Exception as e:
            print(f'요약 생성 오류: {str(e)}')

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
