import asyncio
import io
import os
import struct
import wave
from typing import Optional
from django.conf import settings

try:
    from deepgram import AsyncDeepgramClient, DeepgramClient
    DEEPGRAM_AVAILABLE = True
except ImportError:
    DEEPGRAM_AVAILABLE = False


def pcm_to_wav(pcm_data: bytes, sample_rate: int = 16000, channels: int = 1, bits_per_sample: int = 16) -> bytes:
    """Convert raw PCM data to WAV format"""
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(bits_per_sample // 8)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_data)
    return buffer.getvalue()


class STTService:
    """
    Deepgram API를 사용한 실시간 음성-텍스트 변환 서비스
    """

    def __init__(self):
        self.api_key = settings.DEEPGRAM_API_KEY
        self.client = None
        self.connection = None
        self.transcript_queue = asyncio.Queue()
        self.is_connected = False

        # Set API key in environment
        if self.api_key:
            os.environ['DEEPGRAM_API_KEY'] = self.api_key

    async def connect(self):
        """Deepgram 실시간 연결 설정"""
        if not DEEPGRAM_AVAILABLE:
            raise Exception('Deepgram SDK가 설치되지 않았습니다.')

        if not self.api_key:
            raise Exception('DEEPGRAM_API_KEY가 설정되지 않았습니다.')

        try:
            self.client = AsyncDeepgramClient()
            self.is_connected = True
        except Exception as e:
            raise Exception(f'Deepgram 연결 실패: {str(e)}')

    async def transcribe(self, audio_chunk: bytes) -> Optional[str]:
        """
        오디오 청크를 텍스트로 변환
        """
        if not self.is_connected:
            await self.connect()

        try:
            # Convert raw PCM to WAV format
            wav_data = pcm_to_wav(audio_chunk, sample_rate=16000)

            # Use prerecorded API for chunk-based processing
            response = await self.client.listen.v1.media.transcribe_file(
                request=wav_data,
                model='nova-2',
                language='ko',
                smart_format=True,
                punctuate=True
            )

            # Access transcript from response
            if response and response.results:
                channels = response.results.channels
                if channels and len(channels) > 0:
                    alternatives = channels[0].alternatives
                    if alternatives and len(alternatives) > 0:
                        return alternatives[0].transcript or None

            return None

        except Exception as e:
            print(f'트랜스크립션 오류: {str(e)}')
            return None

    async def transcribe_batch(self, audio_data: bytes) -> str:
        """
        배치 모드로 오디오 변환 (비실시간)
        """
        if not DEEPGRAM_AVAILABLE:
            raise Exception('Deepgram SDK가 설치되지 않았습니다.')

        if not self.api_key:
            raise Exception('DEEPGRAM_API_KEY가 설정되지 않았습니다.')

        try:
            client = AsyncDeepgramClient()
            # Convert raw PCM to WAV format
            wav_data = pcm_to_wav(audio_data, sample_rate=16000)

            response = await client.listen.v1.media.transcribe_file(
                request=wav_data,
                model='nova-2',
                language='ko',
                smart_format=True,
                punctuate=True
            )

            if response and response.results:
                channels = response.results.channels
                if channels and len(channels) > 0:
                    alternatives = channels[0].alternatives
                    if alternatives and len(alternatives) > 0:
                        return alternatives[0].transcript or ''

            return ''

        except Exception as e:
            raise Exception(f'배치 트랜스크립션 오류: {str(e)}')

    async def close(self):
        """연결 종료"""
        self.is_connected = False
        self.client = None


class SimplifiedSTTService:
    """
    간소화된 STT 서비스 (HTTP 기반 배치 처리)
    실시간 WebSocket 연결 없이 청크 단위로 처리
    """

    def __init__(self):
        self.api_key = settings.DEEPGRAM_API_KEY
        self.buffer = b''
        self.buffer_duration = 3.0  # 3초 단위로 처리
        self.sample_rate = 16000
        self.bytes_per_second = self.sample_rate * 2  # 16-bit

        # Set API key in environment for SDK
        if self.api_key:
            os.environ['DEEPGRAM_API_KEY'] = self.api_key

    async def transcribe(self, audio_chunk: bytes) -> Optional[str]:
        """
        오디오 청크를 버퍼에 추가하고, 충분히 쌓이면 변환
        """
        self.buffer += audio_chunk

        buffer_threshold = int(self.buffer_duration * self.bytes_per_second)

        if len(self.buffer) >= buffer_threshold:
            audio_to_process = self.buffer
            self.buffer = b''

            return await self._process_audio(audio_to_process)

        return None

    async def _process_audio(self, audio_data: bytes) -> Optional[str]:
        """Deepgram API로 오디오 처리"""
        if not DEEPGRAM_AVAILABLE:
            print('STT error: Deepgram SDK not available')
            return None

        if not self.api_key:
            print('STT error: API key not set')
            return None

        try:
            # Use AsyncDeepgramClient (reads API key from environment)
            client = AsyncDeepgramClient()

            # Convert raw PCM to WAV format
            wav_data = pcm_to_wav(audio_data, self.sample_rate)

            print(f'STT: Processing {len(audio_data)} bytes of audio (WAV: {len(wav_data)} bytes)...')

            response = await client.listen.v1.media.transcribe_file(
                request=wav_data,
                model='nova-2',
                language='ko',
                smart_format=True,
                punctuate=True
            )

            print(f'STT: Got response')

            # Access transcript from response
            if response and response.results:
                channels = response.results.channels
                if channels and len(channels) > 0:
                    alternatives = channels[0].alternatives
                    if alternatives and len(alternatives) > 0:
                        transcript = alternatives[0].transcript
                        print(f'STT: Transcript = "{transcript}"')
                        return transcript if transcript else None

            print('STT: No transcript in response')
            return None

        except Exception as e:
            import traceback
            print(f'STT error: {type(e).__name__}: {str(e)}')
            traceback.print_exc()
            return None

    async def close(self):
        """리소스 정리"""
        self.buffer = b''
