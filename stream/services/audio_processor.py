import asyncio
import subprocess
import json
import re
import shutil
import os
import sys
from typing import AsyncGenerator
from concurrent.futures import ThreadPoolExecutor


class AudioProcessor:
    """
    yt-dlp와 FFmpeg를 사용하여 유튜브 오디오 스트림을 실시간 추출
    """

    def __init__(self, youtube_url: str):
        self.youtube_url = youtube_url
        self.process = None
        self.is_running = False
        self.chunk_size = 4096  # bytes
        self.sample_rate = 16000  # 16kHz for STT
        self._executor = ThreadPoolExecutor(max_workers=2)

        # Find executables
        self.yt_dlp_path = self._find_executable('yt-dlp')
        self.ffmpeg_path = self._find_executable('ffmpeg')

    def _find_executable(self, name: str) -> str:
        """Find executable path"""
        # First check in virtual environment
        if sys.platform == 'win32':
            venv_path = os.path.join(os.path.dirname(sys.executable), f'{name}.exe')
            if os.path.exists(venv_path):
                return venv_path

        # Check WinGet Links (Windows)
        if sys.platform == 'win32':
            winget_links = os.path.expandvars(r'%LOCALAPPDATA%\Microsoft\WinGet\Links')
            winget_path = os.path.join(winget_links, f'{name}.exe')
            if os.path.exists(winget_path):
                return winget_path

            # Check WinGet Packages directly (for FFmpeg)
            if name == 'ffmpeg':
                packages_path = os.path.expandvars(r'%LOCALAPPDATA%\Microsoft\WinGet\Packages')
                if os.path.exists(packages_path):
                    for folder in os.listdir(packages_path):
                        if 'FFmpeg' in folder:
                            ffmpeg_bin = os.path.join(packages_path, folder)
                            for root, dirs, files in os.walk(ffmpeg_bin):
                                if 'ffmpeg.exe' in files:
                                    return os.path.join(root, 'ffmpeg.exe')

        # Use shutil.which as fallback
        found = shutil.which(name)
        if found:
            return found

        # Return name and hope it's in PATH
        return name

    def _run_subprocess(self, cmd: list) -> tuple:
        """Run subprocess synchronously"""
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=False,
                timeout=60
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return -1, b'', b'Timeout expired'
        except Exception as e:
            return -1, b'', str(e).encode()

    async def get_audio_stream_url(self) -> str:
        """yt-dlp를 사용하여 오디오 스트림 URL 추출"""
        # Try different format selectors for compatibility
        format_selectors = [
            'bestaudio/best',  # Best audio, or best if no audio-only
            'bestaudio*',      # Best audio including audio-only streams
            '91/92/93/94/95',  # Common live audio formats
            'worst',           # Fallback to worst quality
        ]

        last_error = None
        for fmt in format_selectors:
            cmd = [
                self.yt_dlp_path,
                '-f', fmt,
                '-g',  # Get URL only
                '--no-playlist',
                self.youtube_url
            ]

            loop = asyncio.get_event_loop()
            returncode, stdout, stderr = await loop.run_in_executor(
                self._executor, self._run_subprocess, cmd
            )

            if returncode == 0 and stdout.strip():
                return stdout.decode(errors='replace').strip()

            last_error = stderr.decode(errors='replace').strip()

        raise Exception(f'yt-dlp error: {last_error}')

    async def get_video_info(self) -> dict:
        """유튜브 비디오 정보 추출"""
        cmd = [
            self.yt_dlp_path,
            '-j',  # JSON output
            '--no-playlist',
            self.youtube_url
        ]

        loop = asyncio.get_event_loop()
        returncode, stdout, stderr = await loop.run_in_executor(
            self._executor, self._run_subprocess, cmd
        )

        if returncode != 0:
            error_msg = stderr.decode(errors='replace').strip()
            raise Exception(f'Video info error: {error_msg}')

        return json.loads(stdout.decode(errors='replace'))

    def _stream_ffmpeg(self, audio_url: str):
        """FFmpeg를 사용하여 오디오 스트리밍 (generator)"""
        cmd = [
            self.ffmpeg_path,
            '-i', audio_url,
            '-vn',  # No video
            '-acodec', 'pcm_s16le',  # 16-bit PCM
            '-ar', str(self.sample_rate),  # Sample rate
            '-ac', '1',  # Mono
            '-f', 's16le',  # Raw format
            '-loglevel', 'error',
            'pipe:1'  # Output to stdout
        ]

        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=self.chunk_size
        )

        try:
            while self.is_running:
                chunk = self.process.stdout.read(self.chunk_size)
                if not chunk:
                    break
                yield chunk
        finally:
            if self.process:
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()

    async def stream_audio(self) -> AsyncGenerator[bytes, None]:
        """
        FFmpeg를 사용하여 오디오를 실시간 스트리밍
        16kHz, mono, 16-bit PCM으로 변환
        """
        self.is_running = True

        try:
            # Get audio stream URL
            audio_url = await self.get_audio_stream_url()

            # Stream audio in thread
            loop = asyncio.get_event_loop()

            def stream_generator():
                for chunk in self._stream_ffmpeg(audio_url):
                    yield chunk

            gen = stream_generator()

            while self.is_running:
                try:
                    chunk = await loop.run_in_executor(
                        self._executor,
                        lambda: next(gen, None)
                    )
                    if chunk is None:
                        break
                    yield chunk
                except StopIteration:
                    break

        except Exception as e:
            raise Exception(f'Audio streaming error: {str(e)}')
        finally:
            await self.stop()

    async def stream_audio_chunks(self, chunk_duration: float = 1.0, overlap: float = 0.2) -> AsyncGenerator[bytes, None]:
        """
        특정 시간 단위로 오디오 청크 스트리밍 (오버랩으로 누락 방지)
        chunk_duration: 청크 길이 (초)
        overlap: 청크 간 오버랩 비율 (0.0 ~ 0.5) - 경계 음성 누락 방지
        """
        bytes_per_second = self.sample_rate * 2  # 16-bit = 2 bytes per sample
        chunk_bytes = int(bytes_per_second * chunk_duration)
        overlap_bytes = int(chunk_bytes * overlap)
        step_bytes = chunk_bytes - overlap_bytes

        buffer = b''

        async for data in self.stream_audio():
            buffer += data

            while len(buffer) >= chunk_bytes:
                yield buffer[:chunk_bytes]
                # 다음 청크를 위해 오버랩 부분 유지 (음성 경계 누락 방지)
                buffer = buffer[step_bytes:]

        # Yield remaining buffer
        if buffer:
            yield buffer

    async def stop(self):
        """스트리밍 중지"""
        self.is_running = False

        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            except Exception:
                pass
            finally:
                self.process = None

    @staticmethod
    def extract_video_id(url: str) -> str:
        """유튜브 URL에서 비디오 ID 추출"""
        patterns = [
            r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([^&\n?#]+)',
            r'youtube\.com\/live\/([^&\n?#]+)'
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)

        return None

    @staticmethod
    def is_live_stream(video_info: dict) -> bool:
        """라이브 스트리밍 여부 확인"""
        return video_info.get('is_live', False) or video_info.get('live_status') == 'is_live'
