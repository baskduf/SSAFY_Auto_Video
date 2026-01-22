# 실시간 유튜브 강의 AI 피드백 시스템

유튜브 라이브/영상의 실시간 음성을 텍스트로 변환하고, AI가 학습 보조 피드백을 제공하는 웹 애플리케이션입니다.

## 주요 기능

- **실시간 자막 생성**: Deepgram API를 사용한 음성-텍스트 변환 (STT)
- **AI 피드백**: Google Gemini를 통한 실시간 학습 보조 피드백
- **강의 요약**: 스트리밍 종료 후 자동 요약 생성
- **WebSocket 통신**: 실시간 양방향 데이터 전송

## 기술 스택

### Backend
- Django 5.x
- Django Channels (WebSocket)
- Daphne (ASGI Server)

### AI/ML Services
- **Deepgram**: 실시간 음성 인식 (STT)
- **Google Gemini**: LLM 기반 피드백 생성

### Audio Processing
- **yt-dlp**: YouTube 오디오 스트림 추출
- **FFmpeg**: 오디오 형식 변환 (PCM 16kHz)

### Frontend
- Vanilla JavaScript
- WebSocket API
- CSS3 (Dark Theme)

## 설치 방법

### 1. 저장소 클론
```bash
git clone https://github.com/baskduf/SSAFY_Auto_Video.git
cd SSAFY_Auto_Video
```

### 2. 가상환경 생성 및 활성화
```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate
```

### 3. 패키지 설치
```bash
pip install -r requirements.txt
```

### 4. 환경 변수 설정
```bash
cp .env.example .env
```

`.env` 파일을 열고 API 키 설정:
```
DEEPGRAM_API_KEY=your_deepgram_api_key
GOOGLE_API_KEY=your_google_gemini_api_key
```

### 5. FFmpeg 설치

**Windows (winget)**:
```bash
winget install --id Gyan.FFmpeg
```

**macOS (Homebrew)**:
```bash
brew install ffmpeg
```

**Ubuntu/Debian**:
```bash
sudo apt install ffmpeg
```

### 6. 서버 실행
```bash
python -m daphne -b 127.0.0.1 -p 8000 config.asgi:application
```

브라우저에서 http://127.0.0.1:8000 접속

## 사용 방법

1. 웹 브라우저에서 http://127.0.0.1:8000 접속
2. 유튜브 URL 입력 (라이브 또는 일반 영상)
3. "시작" 버튼 클릭
4. 실시간 자막 및 AI 피드백 확인
5. "중지" 버튼으로 스트리밍 종료 시 요약 생성

## 프로젝트 구조

```
SSAFY_Auto_Video/
├── config/                 # Django 프로젝트 설정
│   ├── settings.py
│   ├── urls.py
│   └── asgi.py
├── stream/                 # 메인 앱
│   ├── services/           # 서비스 모듈
│   │   ├── audio_processor.py  # yt-dlp, FFmpeg
│   │   ├── stt_service.py      # Deepgram STT
│   │   └── llm_service.py      # Gemini LLM
│   ├── consumers.py        # WebSocket Consumer
│   ├── routing.py          # WebSocket 라우팅
│   └── views.py            # HTTP Views
├── templates/              # HTML 템플릿
├── static/                 # CSS, JavaScript
│   ├── css/style.css
│   └── js/app.js
├── tests/                  # 테스트
│   └── test_integration.py
├── requirements.txt
└── README.md
```

## API 키 발급

### Deepgram
1. https://deepgram.com 회원가입
2. Console에서 API Key 생성
3. `.env`의 `DEEPGRAM_API_KEY`에 설정

### Google Gemini
1. https://ai.google.dev 접속
2. Google AI Studio에서 API Key 생성
3. `.env`의 `GOOGLE_API_KEY`에 설정

## 통합 테스트

```bash
python tests/test_integration.py
```

## 라이선스

MIT License

## 기여

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request
