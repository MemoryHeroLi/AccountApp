"""启动入口：初始化数据库，启动 Flask 并自动打开浏览器。"""
import threading
import webbrowser

from app import create_app
from db import init_db

PORT = 5000


def main():
    init_db()
    app = create_app()
    url = f'http://127.0.0.1:{PORT}'
    threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    app.run(host='127.0.0.1', port=PORT, debug=False)


if __name__ == '__main__':
    main()
