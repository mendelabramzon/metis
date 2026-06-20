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
    assert "Sign in" in body  # identity login (user-id bearer) for the per-workspace surfaces
    assert "/users/me" in body  # whoami validates the signed-in user
    assert "/workspaces" in body  # the workspace switcher + workspace-scoped query
    assert "/upload" in body  # file upload with a visible per-file parse status
    assert "/sources/connectors" in body  # the source-setup form's connector catalog
    assert "New source" in body  # the source-setup form itself
    assert "add as source" in body  # a discovered Telegram chat can be turned into a source
    assert "/contradictions" in body  # the contradiction inbox (resolve / dismiss)
    assert "/spend" in body  # the per-workspace model-spend view
    assert "/providers" in body  # the enabled-models (capability manifest) view
