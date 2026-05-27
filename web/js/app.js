// 早报电台 - 前端应用
(function() {
    'use strict';

    const DATA_URL = 'data/articles.json';
    const AUDIO_DIR = 'audio/';
    const STORAGE_KEY = 'radio_schedule_v2';
    const DEFAULT_SLOTS = [
        { enabled: true, hour: 8, minute: 0 },
        { enabled: true, hour: 12, minute: 0 },
        { enabled: true, hour: 20, minute: 0 },
    ];

    let articles = [];
    let currentIndex = -1;
    let scheduleTimer = null;
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
        if (name.includes('孥孥')) return 'nunu';
        if (name.includes('卢克文')) return 'lukewen';
        if (name.includes('小龙龙')) return 'xiaolonglong';
        if (name.includes('远方青木')) return 'yuanfangqingmu';
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
        // Include time if available and valid
        const hours = d.getHours();
        const mins = d.getMinutes();
        if (hours !== 0 || mins !== 0) {
            return `${month}月${day}日 周${weekdays[d.getDay()]} ${String(hours).padStart(2,'0')}:${String(mins).padStart(2,'0')}`;
        }
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
                <span class="card-date">${formatDate(article.publish_time || article.date)}</span>
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
                    <span>${formatDate(article.publish_time || article.date)}</span>
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
        if (isPlayAll) {
            if (currentIndex < articles.length - 1) {
                showPlayer(currentIndex + 1);
            } else {
                stopPlayAll();
            }
        } else {
            playNext();
        }
    });

    audio.addEventListener('play', updatePlayButton);
    audio.addEventListener('pause', updatePlayButton);

    progressBar.addEventListener('input', () => {
        if (!audio.duration) return;
        audio.currentTime = (progressBar.value / 100) * audio.duration;
    });

    // ============== 定时自动播放 ==============
    const getBeijingNow = () => {
        const now = new Date();
        // Convert to Beijing time (UTC+8)
        const utc = now.getTime() + now.getTimezoneOffset() * 60000;
        return new Date(utc + 8 * 3600000);
    };

    const getScheduleConfig = () => {
        try {
            const saved = localStorage.getItem(STORAGE_KEY);
            if (saved) {
                const parsed = JSON.parse(saved);
                // Migrate from old single-time format
                if (parsed.hour !== undefined && !parsed.slots) {
                    return {
                        enabled: parsed.enabled ?? true,
                        slots: [
                            { enabled: true, hour: parsed.hour, minute: parsed.minute ?? 0 },
                            { enabled: false, hour: 12, minute: 0 },
                            { enabled: false, hour: 20, minute: 0 },
                        ],
                        notifiedDates: {},
                    };
                }
                // Ensure 3 slots exist
                while (parsed.slots.length < 3) {
                    parsed.slots.push({ enabled: false, hour: 9, minute: 0 });
                }
                return parsed;
            }
        } catch(e) {}
        return { enabled: true, slots: DEFAULT_SLOTS.map(s => ({...s})), notifiedDates: {} };
    };

    const saveScheduleConfig = (config) => {
        try { localStorage.setItem(STORAGE_KEY, JSON.stringify(config)); } catch(e) {}
    };

    const getTodayStr = () => {
        const bj = getBeijingNow();
        return `${bj.getFullYear()}-${String(bj.getMonth()+1).padStart(2,'0')}-${String(bj.getDate()).padStart(2,'0')}`;
    };

    const checkAutoPlay = () => {
        const config = getScheduleConfig();
        if (!config.enabled) return;

        const bj = getBeijingNow();
        const hour = bj.getHours();
        const minute = bj.getMinutes();
        const today = getTodayStr();

        // Check each slot
        for (let i = 0; i < config.slots.length; i++) {
            const slot = config.slots[i];
            if (!slot.enabled) continue;
            if (hour !== slot.hour || minute !== slot.minute) continue;

            // Per-slot notification tracking
            const slotNotifiedKey = `${today}-slot${i}`;
            if (config.notifiedDates[slotNotifiedKey]) continue;

            if (articles.length === 0) continue;

            // Mark this slot as notified
            config.notifiedDates[slotNotifiedKey] = true;
            saveScheduleConfig(config);

            // Find today's articles
            const todayArticles = articles.filter(a => a.date === today);

            if (todayArticles.length > 0) {
                showAlarm(`定时播放 (${String(slot.hour).padStart(2,'0')}:${String(slot.minute).padStart(2,'0')})：今日早报共 ${todayArticles.length} 篇，开始连播...`);
                setTimeout(() => {
                    const startIdx = articles.findIndex(a => a.date === today);
                    if (startIdx >= 0) {
                        isPlayAll = true;
                        btnPlayAll.classList.add('playing');
                        btnPlayAll.innerHTML = '&#9646;&#9646; 停止';
                        showPlayer(startIdx);
                    }
                }, 1500);
            } else {
                showAlarm(`定时播放 (${String(slot.hour).padStart(2,'0')}:${String(slot.minute).padStart(2,'0')})：正在播放最新早报...`);
                setTimeout(() => {
                    showPlayer(0);
                }, 1500);
            }
            return; // Only trigger one slot per minute
        }
    };

    const startSchedule = () => {
        if (scheduleTimer) clearInterval(scheduleTimer);
        // Check every 10 seconds (precise to minute)
        scheduleTimer = setInterval(checkAutoPlay, 10000);
        // Also check immediately
        checkAutoPlay();
        console.log('[早报电台] 定时播放已启动');
    };

    // Alarm bar
    const showAlarm = (text) => {
        const bar = document.getElementById('alarm-bar');
        const alarmText = document.getElementById('alarm-text');
        alarmText.textContent = text;
        bar.style.display = 'flex';
        // Send browser notification
        sendNotification('早报电台', text);
        // Auto-hide after 15s
        setTimeout(() => { bar.style.display = 'none'; }, 15000);
    };

    document.getElementById('alarm-dismiss').addEventListener('click', () => {
        document.getElementById('alarm-bar').style.display = 'none';
    });

    // ============== 浏览器通知 ==============
    const requestNotifyPermission = async () => {
        if (!('Notification' in window)) return false;
        if (Notification.permission === 'granted') return true;
        if (Notification.permission === 'denied') return false;
        const result = await Notification.requestPermission();
        return result === 'granted';
    };

    const sendNotification = (title, body) => {
        if (!('Notification' in window) || Notification.permission !== 'granted') return;
        try {
            new Notification(title, {
                body: body,
                icon: 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><text y=".9em" font-size="90">📻</text></svg>',
                tag: 'daily-radio',
            });
        } catch(e) {}
    };

    // ============== UI 控件 ==============
    const scheduleToggle = document.getElementById('schedule-toggle');
    const btnNotify = document.getElementById('btn-notify');
    const btnPlayAll = document.getElementById('btn-play-all');
    const slotElements = document.querySelectorAll('.schedule-slot');

    // Build a helper to read slot UI values
    const readSlotUI = () => {
        const slots = [];
        slotElements.forEach((el, i) => {
            const toggle = el.querySelector('.slot-toggle');
            const hourSel = el.querySelector('.slot-hour');
            const minuteSel = el.querySelector('.slot-minute');
            slots.push({
                enabled: toggle.checked,
                hour: parseInt(hourSel.value),
                minute: parseInt(minuteSel.value),
            });
        });
        return slots;
    };

    // Load saved config
    const initConfig = getScheduleConfig();
    scheduleToggle.checked = initConfig.enabled;
    slotElements.forEach((el, i) => {
        const slot = initConfig.slots[i];
        if (slot) {
            el.querySelector('.slot-toggle').checked = slot.enabled;
            el.querySelector('.slot-hour').value = slot.hour;
            el.querySelector('.slot-minute').value = slot.minute ?? 0;
        }
        // Style disabled slots
        if (!slot || !slot.enabled) el.classList.add('slot-disabled');
    });

    scheduleToggle.addEventListener('change', () => {
        const config = getScheduleConfig();
        config.enabled = scheduleToggle.checked;
        saveScheduleConfig(config);
        // Toggle slot visibility
        document.getElementById('schedule-slots').style.opacity = scheduleToggle.checked ? '1' : '0.4';
        document.getElementById('schedule-slots').style.pointerEvents = scheduleToggle.checked ? 'auto' : 'none';
        if (scheduleToggle.checked) {
            startSchedule();
        } else if (scheduleTimer) {
            clearInterval(scheduleTimer);
            scheduleTimer = null;
        }
    });

    // Slot change handlers
    slotElements.forEach((el, i) => {
        const toggle = el.querySelector('.slot-toggle');
        const hourSel = el.querySelector('.slot-hour');
        const minuteSel = el.querySelector('.slot-minute');

        const saveSlot = () => {
            const config = getScheduleConfig();
            config.slots[i].enabled = toggle.checked;
            config.slots[i].hour = parseInt(hourSel.value);
            config.slots[i].minute = parseInt(minuteSel.value);
            // Clear notification for this slot so it can re-trigger
            const today = getTodayStr();
            delete config.notifiedDates[`${today}-slot${i}`];
            saveScheduleConfig(config);
        };

        toggle.addEventListener('change', () => {
            el.classList.toggle('slot-disabled', !toggle.checked);
            saveSlot();
        });
        hourSel.addEventListener('change', saveSlot);
        minuteSel.addEventListener('change', saveSlot);
    });

    btnNotify.addEventListener('click', async () => {
        const granted = await requestNotifyPermission();
        if (granted) {
            btnNotify.classList.add('notify-on');
            btnNotify.title = '通知已开启';
            // Send a test notification
            sendNotification('早报电台', '通知已开启，到时将自动提醒你收听！');
        } else {
            btnNotify.title = '通知被阻止，请在浏览器设置中允许';
        }
    });

    // Check if notification is already granted
    if ('Notification' in window && Notification.permission === 'granted') {
        btnNotify.classList.add('notify-on');
        btnNotify.title = '通知已开启';
    }

    // ============== 连播全部 ==============
    let isPlayAll = false;

    const playAllArticles = () => {
        if (articles.length === 0) return;
        isPlayAll = true;
        showPlayer(0);
        btnPlayAll.classList.add('playing');
        btnPlayAll.innerHTML = '&#9646;&#9646; 停止';
        showAlarm(`开始连播全部 ${articles.length} 篇文章...`);
    };

    const stopPlayAll = () => {
        isPlayAll = false;
        audio.pause();
        audio.currentTime = 0;
        btnPlayAll.classList.remove('playing');
        btnPlayAll.innerHTML = '&#9654; 连播';
    };

    btnPlayAll.addEventListener('click', () => {
        if (isPlayAll) {
            stopPlayAll();
        } else {
            playAllArticles();
        }
    });

    // Load data
    fetch(DATA_URL)
        .then(r => r.json())
        .then(data => {
            articles = data;
            render();
            // Start schedule after data loaded
            startSchedule();
        })
        .catch(() => {
            articleList.innerHTML = '<p class="loading">数据加载失败，请刷新重试</p>';
        });

    // Expose to global
    window.app = { play: showPlayer };
})();
