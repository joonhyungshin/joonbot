from aiohttp import web

from joonbot.app import app


def main():
    web.run_app(app)


if __name__ == '__main__':
    main()
