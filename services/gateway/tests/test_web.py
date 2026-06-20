"""The gateway serves the context-exoskeleton console (a single-file frontend) at /."""

from __future__ import annotations


def test_root_serves_the_console(client) -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]

    body = resp.text
    assert "Metis" in body
    assert "context exoskeleton" in body
    assert "/actions" in body  # the command / proposed-action surface is wired into the UI
    assert "/telegram/chats" in body  # the Telegram chat-discovery surface too
