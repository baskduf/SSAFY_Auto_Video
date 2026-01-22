from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
import json
import asyncio
from .services.audio_processor import AudioProcessor


def index(request):
    """메인 대시보드 페이지"""
    return render(request, 'stream/index.html')


@csrf_exempt
@require_http_methods(["POST"])
def validate_url(request):
    """유튜브 URL 유효성 검증 API"""
    try:
        data = json.loads(request.body)
        url = data.get('url', '')

        video_id = AudioProcessor.extract_video_id(url)

        if video_id:
            return JsonResponse({
                'valid': True,
                'video_id': video_id,
                'embed_url': f'https://www.youtube.com/embed/{video_id}'
            })
        else:
            return JsonResponse({
                'valid': False,
                'error': '유효하지 않은 유튜브 URL입니다.'
            })

    except json.JSONDecodeError:
        return JsonResponse({
            'valid': False,
            'error': '잘못된 요청 형식입니다.'
        }, status=400)


@csrf_exempt
@require_http_methods(["POST"])
def get_video_info(request):
    """유튜브 비디오 정보 조회 API"""
    try:
        data = json.loads(request.body)
        url = data.get('url', '')

        processor = AudioProcessor(url)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            info = loop.run_until_complete(processor.get_video_info())
        finally:
            loop.close()

        return JsonResponse({
            'success': True,
            'info': {
                'title': info.get('title', ''),
                'duration': info.get('duration', 0),
                'is_live': info.get('is_live', False),
                'thumbnail': info.get('thumbnail', ''),
                'channel': info.get('channel', ''),
            }
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)
