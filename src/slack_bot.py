"""Slack bot entrypoint for childhood photo generation."""

from __future__ import annotations

import logging
import os
import threading
from typing import Optional

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk.web import WebClient

from .replicate_client import ReplicateClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


load_dotenv()

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")
REPLICATE_LORA_VERSION = os.getenv("REPLICATE_LORA_VERSION")
PORT = int(os.getenv("PORT", "3000"))
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")

if not (SLACK_BOT_TOKEN and SLACK_SIGNING_SECRET and REPLICATE_API_TOKEN and REPLICATE_LORA_VERSION):
    raise RuntimeError("Missing required environment variables.")

app = App(token=SLACK_BOT_TOKEN, signing_secret=SLACK_SIGNING_SECRET)
flask_app = Flask(__name__)
handler = SlackRequestHandler(app)
replicate_client = ReplicateClient(REPLICATE_API_TOKEN)
BOT_USER_ID = app.client.auth_test()["user_id"]


def generate_and_reply(
    *,
    client: WebClient,
    channel: str,
    thread_ts: Optional[str],
    prompt: str,
) -> None:
    logger.info(f"Generating image for prompt: {prompt}")
    try:
        response = replicate_client.run_inference(
            version=REPLICATE_LORA_VERSION,
            prompt=prompt,
            aspect_ratio="3:4",
            num_outputs=1,
        )
        logger.info(f"Replicate prediction response: {response}")
        image_urls = response.get("output") or []
        if not image_urls:
            raise RuntimeError("Replicate did not return any image URLs.")
        image_url = image_urls[0]

        post_response = client.chat_postMessage(
            channel=channel,
            thread_ts=thread_ts,
            text=f"Here is your imaginative childhood photo:\n{image_url}",
            attachments=[
                {
                    "fallback": prompt,
                    "image_url": image_url,
                    "title": prompt,
                }
            ],
        )
        logger.info(f"Posted image to Slack channel={channel} url={image_url} response={post_response}")
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Generation failed: {exc}", exc_info=True)
        client.chat_postMessage(
            channel=channel,
            thread_ts=thread_ts,
            text=f"Generation failed: {exc}",
        )


@app.command("/childhood-photo")
def handle_slash_command(ack, respond, command):
    ack()
    prompt = command.get("text", "").strip()
    if not prompt:
        respond("Please provide a prompt, e.g. `/childhood-photo Your 6-year-old self at a science fair`.")
        return

    channel_id = command["channel_id"]
    thread_ts = command.get("thread_ts") or command.get("command_ts")
    respond(f"Got it! Creating: *{prompt}*")

    threading.Thread(
        target=generate_and_reply,
        kwargs={
            "client": app.client,
            "channel": channel_id,
            "thread_ts": thread_ts,
            "prompt": prompt,
        },
        daemon=True,
    ).start()


@app.event("app_mention")
def handle_app_mention(body, say):
    logger.info(f"Received app_mention event: {body}")
    event = body.get("event") or {}
    text = event.get("text", "") or ""
    prompt = text.replace(f"<@{BOT_USER_ID}>", "").strip()
    if not prompt:
        say("Share a creative prompt and I'll generate a childhood photo!")
        return

    channel = event.get("channel")
    thread_ts = event.get("ts")
    say(f"Working on: *{prompt}*")
    threading.Thread(
        target=generate_and_reply,
        kwargs={
            "client": app.client,
            "channel": channel,
            "thread_ts": thread_ts,
            "prompt": prompt,
        },
        daemon=True,
    ).start()


@app.event("message")
def handle_message(body, say):
    logger.info(f"Received message event: {body}")
    event = body.get("event") or {}
    # Skip bot messages and messages without text
    if event.get("bot_id") or event.get("subtype"):
        return
    
    text = event.get("text", "") or ""
    # Check if bot is mentioned
    if f"<@{BOT_USER_ID}>" in text or "LoRA Model" in text:
        prompt = text.replace(f"<@{BOT_USER_ID}>", "").replace("LoRA Model", "").strip()
        if not prompt:
            say("Share a creative prompt and I'll generate a childhood photo!")
            return

        channel = event.get("channel")
        thread_ts = event.get("ts")
        say(f"Working on: *{prompt}*")
        threading.Thread(
            target=generate_and_reply,
            kwargs={
                "client": app.client,
                "channel": channel,
                "thread_ts": thread_ts,
                "prompt": prompt,
            },
            daemon=True,
        ).start()


@flask_app.route("/slack/events", methods=["POST"])
def slack_events() -> tuple[str, int]:
    return handler.handle(request)


@flask_app.route("/healthz", methods=["GET"])
def healthcheck():
    return jsonify({"status": "ok"})


def main() -> None:
    if SLACK_APP_TOKEN:
        logger.info("Starting bot in Socket Mode...")
        handler = SocketModeHandler(app, SLACK_APP_TOKEN)
        handler.start()
    else:
        logger.info(f"Starting bot in HTTP mode on port {PORT}...")
        flask_app.run(host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    try:
        main()
    finally:
        replicate_client.close()


