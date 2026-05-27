// 早报电台 - 前端应用
(function() {
    'use strict';

    const DATA_URL = 'data/articles.json';
    const AUDIO_DIR = 'audio/';

    let articles = [];
    let currentIndex = -1;
    const audio = new Audio();

    // DOM Elements
    const todaySection = document.getElementById('today-section');
    const todayCards = document.getElementById('today-cards');
    const articleList = document.getElementById('article-list');
    const player = document.getElementById('player');
    const playerSource = document.getElementById('player-source');
    const playerTitle = document.getElementById('player-title');
    const btnPlay = document.getElementById('btn-play');
    const btnPrev = document.getElementById('btn-prev');
    const btnNext = document.getElementById('btn-next');
    const progressBar = document.getElementById('progress-bar');
    const timeCurrent = document.getElementById('time-current');
    const timeTotal = document.getElementById('time-total');

    // Source config
    const sourceClass = (name) => {
        if (name.includes('猫笔刀')) return 'maobidao';
        if (name.includes('刘备')) return 'liubei';
        return '';
    };

    const formatDuration = (sec) => {
        if (!sec || !isFinite(sec)) return '0:00';
        const m = Math.floor(sec / 60);
        const s = Math.floor(sec % 60);
        return `${m}:${s.toString().padStart(2, '0')}`;
    };

    const formatDate = (dateStr) => {
        if (!dateStr) return '';
        const d = new Date(dateStr);
        const month = d.getMonth() + 1;
        const day = d.getDate();
        const weekdays = ['日', '一', '二', '三', '四', '五', '六'];
        return `${month}月${day}日 周${weekdays[d.getDay()]}`;
    };

    const getToday = () => {
        const d = new Date();
        return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
    };

    // Create today card
    const createTodayCard = (article) => {
        const cls = sourceClass(article.source);
        const card = document.createElement('div');
        card.className = 'card-today';
        card.innerHTML = `
            <div class="card-header">
                <span class="source-tag ${cls}">${article.source}</span>
                <span class="card-date">${formatDate(article.date)}</span>
            </div>
            <div class="card-title">${article.title}</div>
            <div class="card-actions">
                <button class="btn btn-primary" onclick="app.play(${articles.indexOf(article)})">
                    &#9654; 播放语音
                </button>
                <a href="${article.url}" target="_blank" class="btn btn-outline">
                    &#128196; 阅读原文
                </a>
            </div>
        `;
        return card;
    };

    // Create history card
    const createHistoryCard = (article) => {
        const cls = sourceClass(article.source);
        const card = document.createElement('div');
        card.className = 'history-card';
        card.onclick = () => app.play(articles.indexOf(article));
        card.innerHTML = `
            <div class="play-icon">&#9654;</div>
            <div class="source-dot ${cls}"></div>
            <div class="card-body">
                <div class="card-title">${article.title}</div>
                <div class="card-meta">
                    <span>${article.source}</span>
                    <span class="dot"></span>
                    <span>${formatDate(article.date)}</span>
                </div>
            </div>
        `;
        return card;
    };

    // Render
    const render = () => {
        todayCards.innerHTML = '';
        articleList.innerHTML = '';

        if (!articles.length) {
            articleList.innerHTML = '<p class="loading">暂无文章，请等待自动抓取...</p>';
            return;
        }

        const today = getToday();
        const todayArticles = articles.filter(a => a.date === today);
        const historyArticles = articles.filter(a => a.date !== today);

        // Today
        if (todayArticles.length > 0) {
            todaySection.style.display = 'block';
            todayArticles.forEach(a => todayCards.appendChild(createTodayCard(a)));
        }

        // History
        if (historyArticles.length > 0) {
            historyArticles.forEach(a => articleList.appendChild(createHistoryCard(a)));
        } else if (todayArticles.length === 0) {
            articleList.innerHTML = '<p class="loading">暂无文章，请等待自动抓取...</p>';
        }
    };

    // Player
    const showPlayer = (index) => {
        const article = articles[index];
        if (!article || !article.audio) return;

        currentIndex = index;
        const cls = sourceClass(article.source);

        playerSource.textContent = article.source;
        playerSource.className = `player-source ${cls}`;
        playerTitle.textContent = article.title;

        audio.src = AUDIO_DIR + article.audio;
        audio.load();
        player.style.display = 'block';

        audio.play().catch(() => {});
        updatePlayButton();
    };

    const updatePlayButton = () => {
        btnPlay.innerHTML = audio.paused ? '&#9654;' : '&#9646;&#9646;';
    };

    const playPrev = () => {
        if (currentIndex > 0) showPlayer(currentIndex - 1);
    };

    const playNext = () => {
        if (currentIndex < articles.length - 1) showPlayer(currentIndex + 1);
    };

    // Event listeners
    btnPlay.addEventListener('click', () => {
        if (currentIndex < 0) return;
        if (audio.paused) {
            audio.play().catch(() => {});
        } else {
            audio.pause();
        }
        updatePlayButton();
    });

    btnPrev.addEventListener('click', playPrev);
    btnNext.addEventListener('click', playNext);

    audio.addEventListener('timeupdate', () => {
        if (!audio.duration) return;
        const pct = (audio.currentTime / audio.duration) * 100;
        progressBar.value = pct;
        timeCurrent.textContent = formatDuration(audio.currentTime);
    });

    audio.addEventListener('loadedmetadata', () => {
        timeTotal.textContent = formatDuration(audio.duration);
    });

    audio.addEventListener('ended', () => {
        updatePlayButton();
        playNext();
    });

    audio.addEventListener('play', updatePlayButton);
    audio.addEventListener('pause', updatePlayButton);

    progressBar.addEventListener('input', () => {
        if (!audio.duration) return;
        audio.currentTime = (progressBar.value / 100) * audio.duration;
    });

    // Load data
    fetch(DATA_URL)
        .then(r => r.json())
        .then(data => {
            articles = data;
            render();
        })
        .catch(() => {
            articleList.innerHTML = '<p class="loading">数据加载失败，请刷新重试</p>';
        });

    // Expose to global
    window.app = { play: showPlayer };
})();
