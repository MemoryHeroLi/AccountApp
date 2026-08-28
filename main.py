"""启动入口：初始化数据库，启动 Flask 并自动打开浏览器。"""
import os
import threading
import webbrowser

from app import create_app
from db import init_db

PORT = 5000


def main():
    init_db()
    app = create_app()
    # debug=True 时 Werkzeug 重载器会创建子进程来运行实际服务器。
    # 只在父进程（无 WERKZEUG_RUN_MAIN）打开浏览器，避免弹两个窗口。
    if not os.environ.get('WERKZEUG_RUN_MAIN'):
        url = f'http://127.0.0.1:{PORT}'
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    app.run(host='127.0.0.1', port=PORT, debug=True)


if __name__ == '__main__':
    main()
