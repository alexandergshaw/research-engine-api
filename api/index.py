"""Vercel serverless entrypoint. The @vercel/python runtime serves this WSGI `app`."""

from app import create_app

app = create_app()
