-- 早报电台 - 播放日志表
-- 在 Supabase SQL Editor 中运行此脚本

CREATE TABLE IF NOT EXISTS play_logs (
  id BIGSERIAL PRIMARY KEY,
  ip TEXT NOT NULL DEFAULT 'unknown',
  time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  source TEXT NOT NULL DEFAULT '',
  title TEXT NOT NULL DEFAULT '',
  article_date TEXT NOT NULL DEFAULT '',
  audio TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 索引：按时间倒序查询
CREATE INDEX IF NOT EXISTS idx_play_logs_time ON play_logs (time DESC);

-- 允许匿名读取和写入（个人工具，无需认证）
ALTER TABLE play_logs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow anonymous reads" ON play_logs
  FOR SELECT USING (true);

CREATE POLICY "Allow anonymous inserts" ON play_logs
  FOR INSERT WITH CHECK (true);

-- 自动清理：保留最近 90 天的日志（可选，Supabase cron 或手动执行）
-- DELETE FROM play_logs WHERE created_at < NOW() - INTERVAL '90 days';
