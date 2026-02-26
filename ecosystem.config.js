module.exports = {
  apps: [
    {
      name: 'medical-app',
      script: 'app/main.py',
      interpreter: 'python3',
      instances: 1,
      exec_mode: 'fork',
      
      // 启动时的参数 - 使用环境变量或硬编码 IP/Port
      args: '--host 0.0.0.0 --port 8000 --reload',
      
      // 环境变量
      env: {
        NODE_ENV: 'development',
        HOST: '0.0.0.0',      // 修改这里改变 IP
        PORT: '8000'           // 修改这里改变 Port
      },
      env_production: {
        NODE_ENV: 'production',
        HOST: '0.0.0.0',
        PORT: '8000'
      },
      
      // 日志
      out_file: './logs/pm2-out.log',
      error_file: './logs/pm2-error.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
      
      // 监听文件变化（开发环境）
      watch: ['app'],
      ignore_watch: ['node_modules', '__pycache__', 'tests'],
      watch_delay: 1000,
      
      // 自动重启配置
      max_memory_restart: '500M',
      max_restarts: 10,
      min_uptime: '10s',
      
      // 优雅关闭
      kill_timeout: 5000,
      listen_timeout: 5000,
    }
  ]
};
