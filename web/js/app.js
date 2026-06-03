// 早报电台 - 前端应用
(function() {
    'use strict';

    const DATA_URL = 'data/articles.json';
    const AUDIO_DIR = 'audio/';
    const STORAGE_KEY = 'radio_schedule_v2';
    const LISTENED_KEY = 'radio_listened';
    const PLAY_LOG_KEY = 'radio_play_log';
    const IP_CACHE_KEY = 'radio_ip_cache';

    const SUPABASE_URL = 'https://bkfdqrcpaeaisakmqtua.supabase.co';
    const SUPABASE_ANON_KEY = 'sb_publishable_hewlNcrb0nFfrywdgTIsIg_4nfdQ_';
    const SUPABASE_ENABLED = !!(SUPABASE_URL && SUPABASE_ANON_KEY);
    const supabase = SUPABASE_ENABLED ? window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY) : null;
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
        if (!name) return 'unknown';
        if (name.includes('猫笔刀')) return 'maobidao';
        if (name.includes('刘备')) return 'liubei';
        if (name.includes('孥孥')) return 'nunu';
        if (name.includes('卢克文')) return 'lukewen';
        if (name.includes('小龙龙')) return 'xiaolonglong';
        if (name.includes('远方青木')) return 'yuanfangqingmu';
        if (name.includes('搬砖小组')) return 'banzhuan';
        if (name.includes('龙谈价值')) return 'longtan';
        if (name.includes('格兰投研')) return 'gelan';
        if (name.includes('价值事务所')) return 'jiazhi';
        if (name.includes('棋行者')) return 'qixing';
        if (name.includes('伯格医生')) return 'boge';
        return 'unknown';
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

    // ============== 已听追踪 ==============
    const getListenedSet = () => {
        try {
            return new Set(JSON.parse(localStorage.getItem(LISTENED_KEY) || '[]'));
        } catch(e) { return new Set(); }
    };
    const saveListenedSet = (set) => {
        try { localStorage.setItem(LISTENED_KEY, JSON.stringify([...set])); } catch(e) {}
    };
    const markListened = (article) => {
        if (!article || !article.audio) return;
        const set = getListenedSet();
        set.add(article.audio);
        saveListenedSet(set);
    };
    const isListened = (article) => {
        return article && article.audio && getListenedSet().has(article.audio);
    };
    // Find next unlistened article starting from given index, wraps around
    const findNextUnlistened = (startFrom) => {
        for (let i = startFrom; i < articles.length; i++) {
            if (!isListened(articles[i])) return i;
        }
        return -1; // all remaining are listened
    };

    // ============== 播放日志 (IP + 时间 + 文章) ==============
    let cachedIP = null;

    const getVisitorIP = async () => {
        if (cachedIP) return cachedIP;
        // Check cache
        try {
            const cached = localStorage.getItem(IP_CACHE_KEY);
            if (cached) {
                const { ip, ts } = JSON.parse(cached);
                // Cache for 24 hours
                if (ip && Date.now() - ts < 86400000) {
                    cachedIP = ip;
                    return ip;
                }
            }
        } catch(e) {}
        // Fetch from ipify
        try {
            const resp = await fetch('https://api.ipify.org?format=json');
            const data = await resp.json();
            if (data.ip) {
                cachedIP = data.ip;
                localStorage.setItem(IP_CACHE_KEY, JSON.stringify({ ip: data.ip, ts: Date.now() }));
                return data.ip;
            }
        } catch(e) {}
        return 'unknown';
    };

    const getPlayLogs = () => {
        try {
            return JSON.parse(localStorage.getItem(PLAY_LOG_KEY) || '[]');
        } catch(e) { return []; }
    };

    const savePlayLogs = (logs) => {
        try {
            // Keep last 500 entries
            if (logs.length > 500) logs = logs.slice(0, 500);
            localStorage.setItem(PLAY_LOG_KEY, JSON.stringify(logs));
        } catch(e) {}
    };

    const addPlayLog = async (article) => {
        if (!article || !article.audio) return;
        const ip = await getVisitorIP();
        const now = new Date();
        const bjOffset = 8 * 3600000;
        const bjTime = new Date(now.getTime() + now.getTimezoneOffset() * 60000 + bjOffset);
        const timestamp = bjTime.toISOString().replace('T', ' ').substring(0, 19);
        const entry = {
            ip: ip,
            time: timestamp,
            source: article.source || '',
            title: article.title || '',
            date: article.date || '',
            audio: article.audio || '',
        };

        // 1. 本地存储（始终保存）
        const logs = getPlayLogs();
        logs.unshift(entry);
        savePlayLogs(logs);

        // 2. 上传到 Supabase（异步，不阻塞播放）
        if (supabase) {
            supabase.from('play_logs').insert([{
                ip: entry.ip,
                time: entry.time,
                source: entry.source,
                title: entry.title,
                article_date: entry.date,
                audio: entry.audio,
            }]).then(({ error }) => {
                if (error) console.warn('[播放日志] Supabase上传失败:', error.message);
            });
        }
    };

    // 从 Supabase 获取远程播放日志
    const fetchRemotePlayLogs = async () => {
        if (!supabase) return [];
        try {
            const { data, error } = await supabase
                .from('play_logs')
                .select('ip,time,source,title,article_date,audio')
                .order('time', { ascending: false })
                .limit(200);
            if (error) throw error;
            return (data || []).map(e => ({
                ip: e.ip || 'unknown',
                time: e.time ? e.time.replace('T', ' ').substring(0, 19) : '',
                source: e.source || '',
                title: e.title || '',
                date: e.article_date || '',
                audio: e.audio || '',
            }));
        } catch (err) {
            console.warn('[播放日志] Supabase获取失败:', err);
            return [];
        }
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
                <button class="btn btn-outline btn-sm" onclick="event.stopPropagation();app.markListened(${articles.indexOf(article)})" title="标记已听">
                    &#10003;
                </button>
            </div>
        `;
        return card;
    };

    // Create history card
    const createHistoryCard = (article) => {
        const cls = sourceClass(article.source);
        const listened = isListened(article);
        const card = document.createElement('div');
        card.className = 'history-card' + (listened ? ' listened' : '');
        const idx = articles.indexOf(article);
        card.onclick = () => app.play(idx);
        card.innerHTML = `
            <div class="play-icon">${listened ? '&#10003;' : '&#9654;'}</div>
            <div class="source-dot ${cls}"></div>
            <div class="card-body">
                <div class="card-title">${article.title}</div>
                <div class="card-meta">
                    <span>${article.source}</span>
                    <span class="dot"></span>
                    <span>${formatDate(article.publish_time || article.date)}</span>
                    ${listened ? '<span class="listened-badge">已听</span>' : ''}
                </div>
            </div>
            ${!listened ? `<button class="btn-icon btn-mark-listened" onclick="event.stopPropagation();app.markListened(${idx})" title="标记已听">&#10003;</button>` : ''}
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
        // Split: today unlistened → today section; listened + older → history
        const todayUnlistened = articles.filter(a => a.date === today && !isListened(a));
        const historyArticles = articles.filter(a => a.date !== today || isListened(a));

        // Today (only unlistened)
        if (todayUnlistened.length > 0) {
            todaySection.style.display = 'block';
            todayUnlistened.forEach(a => todayCards.appendChild(createTodayCard(a)));
        } else {
            todaySection.style.display = 'none';
        }

        // History (listened today + older articles)
        if (historyArticles.length > 0) {
            historyArticles.forEach(a => articleList.appendChild(createHistoryCard(a)));
        } else if (todayUnlistened.length === 0) {
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
        addPlayLog(article);
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
        // Mark current article as listened
        if (currentIndex >= 0 && articles[currentIndex]) {
            markListened(articles[currentIndex]);
        }
        if (isPlayAll) {
            render(); // Re-render to move listened article to history
            // Find next unlistened article
            const nextIndex = findNextUnlistened(currentIndex + 1);
            if (nextIndex >= 0) {
                showPlayer(nextIndex);
            } else {
                stopPlayAll();
            }
        } else {
            // Single play: don't auto-advance, just mark as listened and re-render
            render();
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

    // Try autoplay; returns a Promise. On iOS without user gesture, it rejects.
    const tryAutoPlay = (index) => {
        const article = articles[index];
        if (!article || !article.audio) return Promise.reject('no audio');

        currentIndex = index;
        const cls = sourceClass(article.source);
        playerSource.textContent = article.source;
        playerSource.className = `player-source ${cls}`;
        playerTitle.textContent = article.title;
        audio.src = AUDIO_DIR + article.audio;
        audio.load();
        player.style.display = 'block';

        const promise = audio.play();
        updatePlayButton();
        addPlayLog(article);
        return promise !== undefined ? promise : Promise.resolve();
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

            const timeStr = `${String(slot.hour).padStart(2,'0')}:${String(slot.minute).padStart(2,'0')}`;
            const todayArticles = articles.filter(a => a.date === today);

            if (todayArticles.length > 0) {
                const startIdx = articles.findIndex(a => a.date === today);
                if (startIdx >= 0) {
                    isPlayAll = true;
                    btnPlayAll.classList.add('playing');
                    btnPlayAll.innerHTML = '&#9646;&#9646; 停止';

                    tryAutoPlay(startIdx).then(() => {
                        // Autoplay succeeded (desktop, or iOS after previous interaction)
                        showAlarm(`定时播放 (${timeStr})：今日早报共 ${todayArticles.length} 篇，开始连播...`);
                    }).catch(() => {
                        // Autoplay blocked (iOS Safari/Chrome) — show clickable button
                        showAlarm(
                            `定时播放 (${timeStr})：今日早报共 ${todayArticles.length} 篇，请点此播放`,
                            { text: '\u25B6 点击播放', handler: () => {
                                audio.play().catch(() => {});
                                updatePlayButton();
                            }}
                        );
                    });
                }
            } else {
                tryAutoPlay(0).then(() => {
                    showAlarm(`定时播放 (${timeStr})：正在播放最新早报...`);
                }).catch(() => {
                    showAlarm(
                        `定时播放 (${timeStr})：正在播放最新早报，请点此播放`,
                        { text: '\u25B6 点击播放', handler: () => {
                            audio.play().catch(() => {});
                            updatePlayButton();
                        }}
                    );
                });
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
    let alarmHideTimer = null;

    const showAlarm = (text, action) => {
        const bar = document.getElementById('alarm-bar');
        const alarmText = document.getElementById('alarm-text');
        const alarmAction = document.getElementById('alarm-action');

        alarmText.textContent = text;
        bar.style.display = 'flex';

        // Clear previous hide timer
        if (alarmHideTimer) {
            clearTimeout(alarmHideTimer);
            alarmHideTimer = null;
        }

        // Action button (for iOS autoplay fallback)
        if (action) {
            alarmAction.textContent = action.text;
            alarmAction.style.display = 'inline-block';
            alarmAction.onclick = () => {
                action.handler();
                bar.style.display = 'none';
                if (alarmHideTimer) {
                    clearTimeout(alarmHideTimer);
                    alarmHideTimer = null;
                }
            };
        } else {
            alarmAction.style.display = 'none';
            alarmAction.onclick = null;
            // Auto-hide after 15s only when no action needed
            alarmHideTimer = setTimeout(() => { bar.style.display = 'none'; }, 15000);
        }

        // Send browser notification
        sendNotification('早报电台', text);
    };

    document.getElementById('alarm-dismiss').addEventListener('click', () => {
        document.getElementById('alarm-bar').style.display = 'none';
        if (alarmHideTimer) {
            clearTimeout(alarmHideTimer);
            alarmHideTimer = null;
        }
    });

    // ============== 帮助弹窗 ==============
    const helpModal = document.getElementById('help-modal');
    document.getElementById('btn-help').addEventListener('click', () => {
        helpModal.style.display = 'block';
    });
    document.getElementById('help-close').addEventListener('click', () => {
        helpModal.style.display = 'none';
    });
    document.querySelector('.help-overlay').addEventListener('click', () => {
        helpModal.style.display = 'none';
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

    // ============== 声控指令 (Web Speech API) ==============
    // When voice is ON: audio pauses so mic can hear user clearly.
    // After command: if command didn't explicitly pause/stop, audio auto-resumes.
    const btnVoice = document.getElementById('btn-voice');
    const voiceToast = document.getElementById('voice-toast');
    const voiceToastText = document.getElementById('voice-toast-text');
    let voiceActive = false;
    let recognition = null;
    let voiceToastTimer = null;
    let _wasPlayingBefore = false; // Was audio playing when voice was activated?
    let _resumeTimer = null;       // Timer to auto-resume after unrecognized command

    // Check browser support
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    const isVoiceSupported = !!SpeechRecognition;

    // Hide mic button if not supported (iOS Safari)
    if (!isVoiceSupported) {
        btnVoice.style.display = 'none';
    }

    const showVoiceToast = (text, duration) => {
        if (voiceToastTimer) clearTimeout(voiceToastTimer);
        voiceToastText.textContent = text;
        voiceToast.style.display = 'flex';
        if (duration) {
            voiceToastTimer = setTimeout(() => { voiceToast.style.display = 'none'; }, duration);
        }
    };

    const hideVoiceToast = () => {
        if (voiceToastTimer) clearTimeout(voiceToastTimer);
        voiceToast.style.display = 'none';
    };

    // Cancel any pending auto-resume
    const cancelResume = () => {
        if (_resumeTimer) { clearTimeout(_resumeTimer); _resumeTimer = null; }
    };

    // Auto-resume audio after delay (for unrecognized commands)
    const scheduleResume = (delay = 2500) => {
        cancelResume();
        _resumeTimer = setTimeout(() => {
            if (voiceActive && _wasPlayingBefore && audio.paused && currentIndex >= 0) {
                audio.play().catch(() => {});
                updatePlayButton();
            }
        }, delay);
    };

    // Returns true if the command explicitly controls playback (don't auto-resume)
    const processVoiceCommand = (transcript) => {
        const t = transcript.trim();
        console.log('[早报电台] 声控指令:', t);

        // Normalize: remove spaces
        const cmd = t.replace(/\s/g, '');
        let isPlaybackCommand = true; // By default, don't auto-resume

        if (cmd.includes('下一篇') || cmd.includes('下一个') || cmd.includes('下一曲')) {
            playNext();
            showVoiceToast('▶ 下一篇', 2000);
            // playNext calls showPlayer which auto-plays — don't resume
        } else if (cmd.includes('上一篇') || cmd.includes('上一个') || cmd.includes('上一曲')) {
            playPrev();
            showVoiceToast('▶ 上一篇', 2000);
        } else if (cmd.includes('暂停') || cmd.includes('停止播') || cmd === '停') {
            audio.pause();
            updatePlayButton();
            _wasPlayingBefore = false; // User explicitly paused, don't resume
            showVoiceToast('⏸ 已暂停', 2000);
        } else if (cmd.includes('播放') || cmd.includes('开始') || cmd.includes('继续')) {
            if (currentIndex < 0 && articles.length > 0) {
                showPlayer(0);
            } else {
                audio.play().catch(() => {});
                updatePlayButton();
            }
            showVoiceToast('▶ 播放', 2000);
        } else if (cmd.includes('连播') || cmd.includes('全部播放') || cmd.includes('播放全部')) {
            if (!isPlayAll) {
                playAllArticles();
            }
            showVoiceToast('▶ 连播全部', 2000);
        } else if (cmd.includes('停止') || cmd.includes('取消连播') || cmd.includes('退出')) {
            if (isPlayAll) stopPlayAll();
            audio.pause();
            audio.currentTime = 0;
            updatePlayButton();
            _wasPlayingBefore = false; // User explicitly stopped
            showVoiceToast('⏹ 已停止', 2000);
        } else if (cmd.includes('第一篇') || cmd.includes('从头')) {
            if (articles.length > 0) showPlayer(0);
            showVoiceToast('▶ 第一篇', 2000);
        } else if (cmd.includes('最后一篇') || cmd.includes('最后')) {
            if (articles.length > 0) showPlayer(articles.length - 1);
            showVoiceToast('▶ 最后一篇', 2000);
        } else {
            isPlaybackCommand = false;
            showVoiceToast('❓ 未识别: ' + t, 2500);
        }
        return isPlaybackCommand;
    };

    const startVoice = () => {
        if (!isVoiceSupported) return;
        if (recognition) {
            recognition.abort();
        }
        recognition = new SpeechRecognition();
        recognition.lang = 'zh-CN';
        recognition.continuous = true;
        recognition.interimResults = false;

        recognition.onstart = () => {
            voiceActive = true;
            btnVoice.classList.add('voice-on');
            // Pause audio so mic can hear user clearly
            _wasPlayingBefore = !audio.paused && currentIndex >= 0;
            if (_wasPlayingBefore) {
                audio.pause();
                updatePlayButton();
            }
            showVoiceToast('🎤 正在聆听... 试试说「播放」「下一篇」「暂停」', 0);
        };

        recognition.onresult = (event) => {
            cancelResume();
            for (let i = event.resultIndex; i < event.results.length; i++) {
                if (event.results[i].isFinal) {
                    const handled = processVoiceCommand(event.results[i][0].transcript);
                    // If command was not recognized, schedule auto-resume
                    if (!handled) {
                        scheduleResume(2500);
                    }
                }
            }
        };

        recognition.onerror = (event) => {
            if (event.error === 'not-allowed') {
                showVoiceToast('麦克风权限被拒绝', 3000);
                stopVoice();
            } else if (event.error === 'no-speech') {
                // Chrome fires this when only ambient noise — silently restart
            } else if (event.error === 'aborted') {
                // User-initiated stop, do nothing
            } else {
                console.warn('[早报电台] 语音识别错误:', event.error);
            }
        };

        recognition.onend = () => {
            // Auto-restart if still active (recognition stops after each result)
            if (voiceActive) {
                try { recognition.start(); } catch(e) {}
            }
        };

        try {
            recognition.start();
        } catch(e) {
            showVoiceToast('启动语音失败', 2000);
        }
    };

    const stopVoice = () => {
        voiceActive = false;
        cancelResume();
        btnVoice.classList.remove('voice-on');
        hideVoiceToast();
        // Resume audio if it was playing before voice was activated
        if (_wasPlayingBefore && audio.paused && currentIndex >= 0) {
            audio.play().catch(() => {});
            updatePlayButton();
        }
        _wasPlayingBefore = false;
        if (recognition) {
            try { recognition.abort(); } catch(e) {}
            recognition = null;
        }
    };

    btnVoice.addEventListener('click', () => {
        if (voiceActive) {
            stopVoice();
        } else {
            startVoice();
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
    window.app = { play: showPlayer, markListened: (idx) => { markListened(articles[idx]); render(); } };

    // ============== 运行日志查看器 ==============
    const btnLog = document.getElementById('btn-log');
    const logModal = document.getElementById('log-modal');
    const logClose = document.getElementById('log-close');
    const logOverlay = document.querySelector('.log-overlay');
    const logBody = document.getElementById('log-body');

    const statusMap = { ok: '✅', fail: '❌', skip: '⏭️' };
    const modeColor = { '本地': '#2d6a4f', 'AI自动化': '#e76f51', 'CI': '#1982c4' };

    async function loadRunLog() {
        logBody.innerHTML = '<p class="loading">加载中...</p>';
        try {
            const resp = await fetch('data/tts_run_log.json?t=' + Date.now());
            const data = await resp.json();
            if (!data || data.length === 0) {
                logBody.innerHTML = '<p class="log-empty">暂无运行日志</p>';
                return;
            }
            // Group by date
            const grouped = {};
            data.forEach(e => {
                const date = (e.timestamp || '').substring(0, 10);
                if (!grouped[date]) grouped[date] = [];
                grouped[date].push(e);
            });
            let html = '';
            for (const [date, entries] of Object.entries(grouped)) {
                html += `<div class="log-date">${date}</div>`;
                html += '<div class="log-entries">';
                entries.forEach(e => {
                    const time = (e.timestamp || '').substring(11, 19);
                    const icon = statusMap[e.status] || '❓';
                    const modeStyle = modeColor[e.mode] ? `style="color:${modeColor[e.mode]}"` : '';
                    const audioStr = e.audio ? `<span class="log-audio">${e.audio}</span>` : '';
                    const reasonStr = e.reason ? `<span class="log-reason">${e.reason}</span>` : '';
                    html += `<div class="log-entry">
                        <span class="log-icon">${icon}</span>
                        <span class="log-time">${time}</span>
                        <span class="log-source" ${modeStyle}>${e.source || '?'}</span>
                        <span class="log-title">${(e.title || '').substring(0, 30)}</span>
                        ${audioStr}${reasonStr}
                    </div>`;
                });
                html += '</div>';
            }
            logBody.innerHTML = html;
        } catch (err) {
            logBody.innerHTML = `<p class="log-empty">加载失败: ${err.message}</p>`;
        }
    }

    btnLog.addEventListener('click', () => {
        logModal.style.display = 'block';
        loadRunLog();
    });
    logClose.addEventListener('click', () => { logModal.style.display = 'none'; });
    logOverlay.addEventListener('click', () => { logModal.style.display = 'none'; });

    // ============== 播放日志查看器 ==============
    const btnPlayLog = document.getElementById('btn-play-log');
    const playLogModal = document.getElementById('playlog-modal');
    const playLogClose = document.getElementById('playlog-close');
    const playLogOverlay = document.querySelector('.playlog-overlay');
    const playLogBody = document.getElementById('playlog-body');

    const renderPlayLogs = async () => {
        playLogBody.innerHTML = '<p class="loading">加载中...</p>';

        // 获取远程日志
        const remoteLogs = await fetchRemotePlayLogs();
        const localLogs = getPlayLogs();

        // 合并去重：以 (ip, time, source, title) 为唯一键
        const seen = new Set();
        const merged = [];
        const addEntry = (e) => {
            const key = `${e.ip}|${e.time}|${e.source}|${e.title}`;
            if (!seen.has(key)) {
                seen.add(key);
                merged.push(e);
            }
        };
        // 远程优先（更完整），本地补充
        remoteLogs.forEach(addEntry);
        localLogs.forEach(addEntry);

        // 按时间倒序
        merged.sort((a, b) => (b.time || '').localeCompare(a.time || ''));

        if (merged.length === 0) {
            playLogBody.innerHTML = '<p class="log-empty">暂无播放记录</p>';
            return;
        }

        // 标记数据来源
        const isRemote = (e) => remoteLogs.some(r => r.ip === e.ip && r.time === e.time && r.source === e.source && r.title === e.title);

        // Group by date
        const grouped = {};
        merged.forEach(e => {
            const date = (e.time || '').substring(0, 10);
            if (!grouped[date]) grouped[date] = [];
            grouped[date].push(e);
        });
        let html = '';
        if (SUPABASE_ENABLED) {
            html += `<div class="playlog-sync-badge">☁️ 已同步 (${remoteLogs.length} 条远程, ${localLogs.length} 条本地)</div>`;
        } else {
            html += `<div class="playlog-sync-badge">💾 仅本地存储 (未配置云端同步)</div>`;
        }
        for (const [date, entries] of Object.entries(grouped)) {
            html += `<div class="log-date">${date}</div>`;
            html += '<div class="log-entries">';
            entries.forEach(e => {
                const time = (e.time || '').substring(11, 19);
                const cls = sourceClass(e.source);
                const remote = isRemote(e);
                html += `<div class="log-entry">
                    <span class="log-icon">🎧</span>
                    <span class="log-time">${time}</span>
                    <span class="playlog-ip">${e.ip || '?'}</span>
                    <span class="log-source ${cls}">${e.source || '?'}</span>
                    <span class="log-title">${(e.title || '').substring(0, 30)}</span>
                    ${remote ? '<span class="playlog-cloud">☁</span>' : ''}
                </div>`;
            });
            html += '</div>';
        }
        playLogBody.innerHTML = html;
    };

    btnPlayLog.addEventListener('click', () => {
        playLogModal.style.display = 'block';
        renderPlayLogs();
    });
    playLogClose.addEventListener('click', () => { playLogModal.style.display = 'none'; });
    playLogOverlay.addEventListener('click', () => { playLogModal.style.display = 'none'; });
})();
