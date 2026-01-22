# -*- coding: utf-8 -*-
"""
Real-time YouTube Lecture AI Feedback System - Integration Test
"""

import os
import sys
import asyncio
import io
from pathlib import Path

# Set stdout encoding to UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add project root to Python path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from django.conf import settings


# Test URL
TEST_YOUTUBE_URL = "https://www.youtube.com/watch?v=GC-MIB7XQ2s"


def print_header(title: str):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def print_result(test_name: str, success: bool, message: str = ""):
    status = "[PASS]" if success else "[FAIL]"
    print(f"\n{status} {test_name}")
    if message:
        print(f"    -> {message}")


class IntegrationTest:
    def __init__(self):
        self.results = []

    async def test_1_environment_check(self):
        """Environment Check"""
        print_header("1. Environment Check")

        # Deepgram API Key
        deepgram_key = settings.DEEPGRAM_API_KEY
        success = bool(deepgram_key and len(deepgram_key) > 10)
        print_result("Deepgram API Key", success,
                    f"Set ({deepgram_key[:10]}...)" if success else "Not set")
        self.results.append(("Deepgram API Key", success))

        # Google API Key
        google_key = settings.GOOGLE_API_KEY
        success = bool(google_key and len(google_key) > 10)
        print_result("Google API Key", success,
                    f"Set ({google_key[:10]}...)" if success else "Not set")
        self.results.append(("Google API Key", success))

        return all(r[1] for r in self.results[-2:])

    async def test_2_audio_processor(self):
        """Audio Processor Test (yt-dlp)"""
        print_header("2. Audio Processor Test (yt-dlp)")

        from stream.services.audio_processor import AudioProcessor

        processor = AudioProcessor(TEST_YOUTUBE_URL)

        # Video ID extraction test
        video_id = processor.extract_video_id(TEST_YOUTUBE_URL)
        success = video_id is not None
        print_result("Video ID Extraction", success, f"ID: {video_id}" if success else "Failed")
        self.results.append(("Video ID Extraction", success))

        if not success:
            return False

        # Video info test
        try:
            print("\n    Getting video info...")
            info = await processor.get_video_info()
            success = 'title' in info
            title = info.get('title', '')[:50]
            print_result("Video Info", success, f"Title: {title}..." if success else "Failed")
            self.results.append(("Video Info", success))
        except Exception as e:
            import traceback
            print_result("Video Info", False, f"{type(e).__name__}: {str(e)}")
            traceback.print_exc()
            self.results.append(("Video Info", False))
            return False

        # Audio stream URL test
        try:
            print("\n    Extracting audio stream URL...")
            audio_url = await processor.get_audio_stream_url()
            success = audio_url and audio_url.startswith('http')
            print_result("Audio Stream URL", success,
                        f"URL length: {len(audio_url)} chars" if success else "Failed")
            self.results.append(("Audio Stream URL", success))
        except Exception as e:
            print_result("Audio Stream URL", False, str(e))
            self.results.append(("Audio Stream URL", False))
            return False

        return True

    async def test_3_audio_streaming(self):
        """Audio Streaming Test (FFmpeg)"""
        print_header("3. Audio Streaming Test (FFmpeg)")

        from stream.services.audio_processor import AudioProcessor

        processor = AudioProcessor(TEST_YOUTUBE_URL)

        try:
            print("\n    Streaming audio chunks (5 seconds)...")
            chunks_received = 0
            total_bytes = 0

            async for chunk in processor.stream_audio_chunks(chunk_duration=1.0):
                chunks_received += 1
                total_bytes += len(chunk)
                print(f"    -> Chunk #{chunks_received}: {len(chunk)} bytes")

                if chunks_received >= 5:  # 5 seconds only
                    break

            await processor.stop()

            success = chunks_received >= 3 and total_bytes > 10000
            print_result("Audio Streaming", success,
                        f"{chunks_received} chunks, {total_bytes:,} bytes total")
            self.results.append(("Audio Streaming", success))

            return success, chunks_received > 0

        except Exception as e:
            print_result("Audio Streaming", False, str(e))
            self.results.append(("Audio Streaming", False))
            return False, False

    async def test_4_stt_service(self, audio_chunks: list = None):
        """STT Service Test (Deepgram)"""
        print_header("4. STT Service Test (Deepgram)")

        from stream.services.stt_service import SimplifiedSTTService
        from stream.services.audio_processor import AudioProcessor

        stt = SimplifiedSTTService()

        if not settings.DEEPGRAM_API_KEY:
            print_result("STT Service", False, "API key not set")
            self.results.append(("STT Service", False))
            return False, None

        try:
            # Collect real audio data
            print("\n    Collecting audio data (10 seconds)...")
            processor = AudioProcessor(TEST_YOUTUBE_URL)
            audio_buffer = b''

            async for chunk in processor.stream_audio_chunks(chunk_duration=2.0):
                audio_buffer += chunk
                if len(audio_buffer) >= 16000 * 2 * 10:  # 10 seconds
                    break

            await processor.stop()

            print(f"    -> Collected audio: {len(audio_buffer):,} bytes")

            # STT conversion
            print("\n    Converting speech to text...")
            transcript = await stt._process_audio(audio_buffer)

            success = transcript and len(transcript) > 10
            if success:
                print_result("STT Conversion", success, f"Result: \"{transcript[:100]}...\"")
            else:
                print_result("STT Conversion", False, "Conversion failed or empty result")
            self.results.append(("STT Conversion", success))

            await stt.close()
            return success, transcript

        except Exception as e:
            print_result("STT Service", False, str(e))
            self.results.append(("STT Service", False))
            return False, None

    async def test_5_llm_service(self, context: str = None):
        """LLM Service Test (Google Gemini)"""
        print_header("5. LLM Service Test (Google Gemini)")

        from stream.services.llm_service import LLMService

        llm = LLMService()

        if not settings.GOOGLE_API_KEY:
            print_result("LLM Service", False, "API key not set")
            self.results.append(("LLM Service", False))
            return False

        # Test context
        test_context = context or """
        Today we will learn about the basics of Python programming.
        Variables are spaces that store data.
        In Python, you don't need to specify the type when declaring variables.
        For example, x = 10 makes x an integer variable.
        Functions are code blocks that perform specific tasks.
        """

        try:
            print("\n    Generating feedback...")
            feedback = await llm.generate_feedback(test_context)

            success = feedback and len(feedback) > 20
            if success:
                print_result("LLM Feedback Generation", success, f"\n    Feedback: {feedback[:300]}...")
            else:
                print_result("LLM Feedback Generation", False, "Generation failed")
            self.results.append(("LLM Feedback Generation", success))

            return success

        except Exception as e:
            print_result("LLM Service", False, str(e))
            self.results.append(("LLM Service", False))
            return False

    async def test_6_full_pipeline(self):
        """Full Pipeline Test"""
        print_header("6. Full Pipeline Test")

        from stream.services.audio_processor import AudioProcessor
        from stream.services.stt_service import SimplifiedSTTService
        from stream.services.llm_service import LLMService

        processor = AudioProcessor(TEST_YOUTUBE_URL)
        stt = SimplifiedSTTService()
        llm = LLMService()

        transcripts = []

        try:
            print("\n    Running pipeline...")
            print("    [Audio Extraction] -> [STT Conversion] -> [LLM Feedback]")

            # Collect 15 seconds of audio and convert to text
            print("\n    Step 1: Audio collection and STT (15 seconds)...")
            chunk_count = 0

            async for chunk in processor.stream_audio_chunks(chunk_duration=3.0):
                chunk_count += 1
                transcript = await stt.transcribe(chunk)

                if transcript:
                    transcripts.append(transcript)
                    display_text = transcript[:50] if len(transcript) > 50 else transcript
                    print(f"    -> [{chunk_count}] \"{display_text}...\"")

                if chunk_count >= 5:  # 15 seconds
                    break

            await processor.stop()

            if not transcripts:
                print_result("Pipeline - STT", False, "No transcripts")
                self.results.append(("Full Pipeline", False))
                return False

            print(f"\n    Total {len(transcripts)} transcripts collected")

            # Generate LLM feedback
            print("\n    Step 2: Generating LLM feedback...")
            context = ' '.join(transcripts)
            feedback = await llm.generate_feedback(context)

            if feedback:
                print(f"\n    [AI Feedback]\n    {feedback}")
                success = True
            else:
                print("    Feedback generation failed")
                success = False

            print_result("Full Pipeline", success,
                        f"{len(transcripts)} transcripts -> Feedback generated" if success else "Failed")
            self.results.append(("Full Pipeline", success))

            return success

        except Exception as e:
            print_result("Full Pipeline", False, str(e))
            self.results.append(("Full Pipeline", False))
            return False

    def print_summary(self):
        """Test Results Summary"""
        print_header("Test Results Summary")

        passed = sum(1 for _, success in self.results if success)
        total = len(self.results)

        print(f"\n  Passed: {passed}/{total}")
        print()

        for name, success in self.results:
            status = "[O]" if success else "[X]"
            print(f"  {status} {name}")

        print()

        if passed == total:
            print("  === ALL TESTS PASSED! ===")
        else:
            print(f"  === {total - passed} TEST(S) FAILED ===")

        print()


async def run_tests():
    """Run tests"""
    print("\n" + "=" * 60)
    print("  Real-time YouTube Lecture AI Feedback System")
    print("  Integration Test")
    print("  Test URL:", TEST_YOUTUBE_URL)
    print("=" * 60)

    tester = IntegrationTest()

    # 1. Environment check
    await tester.test_1_environment_check()

    # 2. Audio processor test
    await tester.test_2_audio_processor()

    # 3. Audio streaming test
    await tester.test_3_audio_streaming()

    # 4. STT service test
    await tester.test_4_stt_service()

    # 5. LLM service test
    await tester.test_5_llm_service()

    # 6. Full pipeline test
    await tester.test_6_full_pipeline()

    # Summary
    tester.print_summary()


if __name__ == "__main__":
    asyncio.run(run_tests())
