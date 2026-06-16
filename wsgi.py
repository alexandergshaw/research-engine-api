"""WSGI entrypoint. `flask --app wsgi run` for dev; gunicorn/waitress in prod."""

from app import create_app

app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
