/**
 * 실시간 유튜브 강의 AI 피드백 시스템
 * WebSocket 기반 클라이언트
 */

class StreamApp {
    constructor() {
        // DOM Elements
        this.urlInput = document.getElementById('youtube-url');
        this.startBtn = document.getElementById('start-btn');
        this.stopBtn = document.getElementById('stop-btn');
        this.urlError = document.getElementById('url-error');
        this.videoPlaceholder = document.getElementById('video-placeholder');
        this.youtubeIframe = document.getElementById('youtube-iframe');
        this.videoThumbnailLink = document.getElementById('video-thumbnail-link');
        this.videoThumbnail = document.getElementById('video-thumbnail');
        this.videoInfo = document.getElementById('video-info');
        this.videoTitle = document.getElementById('video-title');
        this.videoChannel = document.getElementById('video-channel');
        this.liveBadge = document.getElementById('video-live-badge');
        this.statusIndicator = document.getElementById('status-indicator');
        this.connectionStatus = document.getElementById('connection-status');
        this.transcriptContainer = document.getElementById('transcript-container');
        this.feedbackContainer = document.getElementById('feedback-container');

        // State
        this.socket = null;
        this.isStreaming = false;
        this.transcripts = [];
        this.feedbacks = [];

        // Initialize
        this.init();
    }

    init() {
        // Event Listeners
        this.startBtn.addEventListener('click', () => this.startStreaming());
        this.stopBtn.addEventListener('click', () => this.stopStreaming());
        this.urlInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.startStreaming();
        });
        this.urlInput.addEventListener('input', () => this.hideError());

        // Check for URL parameter
        const urlParams = new URLSearchParams(window.location.search);
        const videoUrl = urlParams.get('url');
        if (videoUrl) {
            this.urlInput.value = videoUrl;
        }
    }

    // WebSocket Connection
    connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/stream/`;

        this.socket = new WebSocket(wsUrl);

        this.socket.onopen = () => {
            console.log('WebSocket connected');
            this.updateConnectionStatus(true);
        };

        this.socket.onmessage = (event) => {
            const data = JSON.parse(event.data);
            this.handleMessage(data);
        };

        this.socket.onclose = (event) => {
            console.log('WebSocket closed:', event.code);
            this.updateConnectionStatus(false);
            if (this.isStreaming) {
                // Attempt reconnection
                setTimeout(() => this.connectWebSocket(), 3000);
            }
        };

        this.socket.onerror = (error) => {
            console.error('WebSocket error:', error);
            this.showError('WebSocket 연결 오류가 발생했습니다.');
        };
    }

    // Handle incoming messages
    handleMessage(data) {
        switch (data.type) {
            case 'connection':
                console.log('Connection status:', data.message);
                break;

            case 'status':
                this.updateStatus(data.status, data.message);
                break;

            case 'transcript':
                this.addTranscript(data.text, data.timestamp);
                break;

            case 'feedback':
                this.addFeedback(data.content, data.timestamp);
                break;

            case 'error':
                this.showError(data.message);
                this.updateStatus('error', data.message);
                break;
        }
    }

    // Start streaming
    async startStreaming() {
        const url = this.urlInput.value.trim();

        if (!url) {
            this.showError('유튜브 URL을 입력해주세요.');
            return;
        }

        // Validate URL
        const validation = await this.validateUrl(url);
        if (!validation.valid) {
            this.showError(validation.error);
            return;
        }

        // Show video (try iframe first, fallback to thumbnail)
        this.showVideo(validation.video_id, validation.embed_url, url);

        // Get video info
        try {
            const info = await this.getVideoInfo(url);
            if (info.success) {
                this.showVideoInfo(info.info);
            }
        } catch (e) {
            console.error('Failed to get video info:', e);
        }

        // Connect WebSocket and start
        this.setLoading(true);
        this.connectWebSocket();

        // Wait for connection
        await new Promise((resolve) => {
            const checkConnection = setInterval(() => {
                if (this.socket && this.socket.readyState === WebSocket.OPEN) {
                    clearInterval(checkConnection);
                    resolve();
                }
            }, 100);

            // Timeout after 5 seconds
            setTimeout(() => {
                clearInterval(checkConnection);
                resolve();
            }, 5000);
        });

        if (this.socket && this.socket.readyState === WebSocket.OPEN) {
            this.socket.send(JSON.stringify({
                action: 'start',
                url: url
            }));
            this.isStreaming = true;
            this.startBtn.style.display = 'none';
            this.stopBtn.style.display = 'flex';
            this.clearContainers();
        } else {
            this.showError('WebSocket 연결에 실패했습니다.');
        }

        this.setLoading(false);
    }

    // Stop streaming
    stopStreaming() {
        if (this.socket && this.socket.readyState === WebSocket.OPEN) {
            this.socket.send(JSON.stringify({
                action: 'stop'
            }));
        }

        this.isStreaming = false;
        this.startBtn.style.display = 'flex';
        this.stopBtn.style.display = 'none';

        if (this.socket) {
            this.socket.close();
            this.socket = null;
        }

        this.updateStatus('stopped', '분석이 중지되었습니다.');
    }

    // Validate YouTube URL
    async validateUrl(url) {
        try {
            const response = await fetch('/api/validate-url/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                body: JSON.stringify({ url })
            });
            return await response.json();
        } catch (error) {
            return { valid: false, error: 'URL 검증 중 오류가 발생했습니다.' };
        }
    }

    // Get video info
    async getVideoInfo(url) {
        try {
            const response = await fetch('/api/video-info/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                body: JSON.stringify({ url })
            });
            return await response.json();
        } catch (error) {
            return { success: false, error: error.message };
        }
    }

    // Show video thumbnail only (iframe embedding often blocked)
    showVideo(videoId, embedUrl, originalUrl) {
        this.videoPlaceholder.style.display = 'none';
        this.youtubeIframe.style.display = 'none';

        // Show thumbnail with link to YouTube
        this.videoThumbnail.src = `https://img.youtube.com/vi/${videoId}/maxresdefault.jpg`;
        this.videoThumbnail.onerror = () => {
            this.videoThumbnail.src = `https://img.youtube.com/vi/${videoId}/hqdefault.jpg`;
        };
        this.videoThumbnailLink.href = originalUrl;
        this.videoThumbnailLink.style.display = 'flex';
    }

    // Show video info
    showVideoInfo(info) {
        this.videoTitle.textContent = info.title;
        this.videoChannel.textContent = info.channel;
        this.liveBadge.style.display = info.is_live ? 'inline-block' : 'none';
        this.videoInfo.style.display = 'block';
    }

    // Add transcript item
    addTranscript(text, timestamp) {
        // Remove empty state
        const emptyState = this.transcriptContainer.querySelector('.empty-state');
        if (emptyState) emptyState.remove();

        const item = document.createElement('div');
        item.className = 'transcript-item';
        item.innerHTML = `
            <div class="timestamp">${this.formatTimestamp(timestamp)}</div>
            <div class="text">${this.escapeHtml(text)}</div>
        `;

        this.transcriptContainer.appendChild(item);
        this.scrollToBottom(this.transcriptContainer);

        this.transcripts.push({ text, timestamp });
    }

    // Add feedback item
    addFeedback(content, timestamp) {
        // Remove empty state
        const emptyState = this.feedbackContainer.querySelector('.empty-state');
        if (emptyState) emptyState.remove();

        const item = document.createElement('div');
        item.className = 'feedback-item';
        item.innerHTML = `
            <div class="timestamp">${this.formatTimestamp(timestamp)}</div>
            <div class="content">${this.formatFeedback(content)}</div>
        `;

        this.feedbackContainer.appendChild(item);
        this.scrollToBottom(this.feedbackContainer);

        this.feedbacks.push({ content, timestamp });

        // Highlight feedback panel briefly
        this.feedbackContainer.closest('.panel')?.classList.add('highlight');
        setTimeout(() => {
            this.feedbackContainer.closest('.panel')?.classList.remove('highlight');
        }, 2000);
    }

    // Format feedback content with markdown support
    formatFeedback(content) {
        // Process code blocks first (before escaping HTML)
        let formatted = content;

        // Handle fenced code blocks with language (```language\ncode```)
        formatted = formatted.replace(/```(\w+)?\n([\s\S]*?)```/g, (match, lang, code) => {
            const langLabel = lang ? `<span class="code-lang">${lang}</span>` : '';
            const escapedCode = this.escapeHtml(code.trim());
            return `<div class="code-block-wrapper">${langLabel}<pre><code>${escapedCode}</code></pre></div>`;
        });

        // Handle inline code (`code`)
        formatted = formatted.replace(/`([^`]+)`/g, (match, code) => {
            return `<code>${this.escapeHtml(code)}</code>`;
        });

        // Handle bold (**text**)
        formatted = formatted.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');

        // Handle italic (*text*)
        formatted = formatted.replace(/\*([^*]+)\*/g, '<em>$1</em>');

        // Handle bullet lists (- item)
        formatted = formatted.replace(/^- (.+)$/gm, '<li>$1</li>');
        formatted = formatted.replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>');

        // Handle newlines (outside of code blocks)
        formatted = formatted.replace(/\n/g, '<br>');

        // Clean up extra <br> after block elements
        formatted = formatted.replace(/<\/pre><\/div><br>/g, '</pre></div>');
        formatted = formatted.replace(/<\/ul><br>/g, '</ul>');

        return formatted;
    }

    // Update status
    updateStatus(status, message) {
        this.statusIndicator.className = 'status-indicator';

        switch (status) {
            case 'starting':
            case 'extracting':
            case 'processing':
                this.statusIndicator.classList.add('processing');
                break;
            case 'streaming':
            case 'active':
                this.statusIndicator.classList.add('active');
                break;
            case 'error':
                this.statusIndicator.classList.add('error');
                break;
        }

        this.statusIndicator.querySelector('.status-text').textContent = message;
    }

    // Update connection status
    updateConnectionStatus(connected) {
        const wsStatus = this.connectionStatus.querySelector('.ws-status');
        wsStatus.className = 'ws-status ' + (connected ? 'connected' : 'disconnected');
        wsStatus.textContent = 'WebSocket: ' + (connected ? '연결됨' : '연결 안됨');
    }

    // Clear containers
    clearContainers() {
        this.transcriptContainer.innerHTML = '<div class="empty-state"><p>분석을 시작하면 실시간 자막이 표시됩니다</p></div>';
        this.feedbackContainer.innerHTML = '<div class="empty-state"><p>강의 내용과 관련된 추가 학습 정보가 표시됩니다</p></div>';
        this.transcripts = [];
        this.feedbacks = [];
    }

    // UI Helpers
    setLoading(loading) {
        const btnText = this.startBtn.querySelector('.btn-text');
        const btnLoading = this.startBtn.querySelector('.btn-loading');

        if (loading) {
            btnText.style.display = 'none';
            btnLoading.style.display = 'flex';
            this.startBtn.disabled = true;
        } else {
            btnText.style.display = 'inline';
            btnLoading.style.display = 'none';
            this.startBtn.disabled = false;
        }
    }

    showError(message) {
        this.urlError.textContent = message;
        this.urlError.style.display = 'block';
    }

    hideError() {
        this.urlError.style.display = 'none';
    }

    scrollToBottom(container) {
        // Use requestAnimationFrame to ensure DOM is updated
        requestAnimationFrame(() => {
            container.scrollTop = container.scrollHeight;
        });
    }

    formatTimestamp(timestamp) {
        if (typeof timestamp === 'number') {
            // Format as elapsed time (MM:SS)
            const totalSeconds = Math.floor(timestamp);
            const minutes = Math.floor(totalSeconds / 60);
            const seconds = totalSeconds % 60;
            return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
        }
        return '00:00';
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    getCSRFToken() {
        const name = 'csrftoken';
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }
}

// Initialize app when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.app = new StreamApp();
});
