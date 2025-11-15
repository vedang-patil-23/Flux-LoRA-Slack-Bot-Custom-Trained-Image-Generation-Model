## Architecture Overview

- **Slack Client**: Users interact via `/childhood-photo` slash command or bot mentions. Slack sends events to our Flask/Bolt endpoint (`/slack/events`).
- **Slack Bot Service**: `src/slack_bot.py` runs a Flask web server that wraps the Slack Bolt app. It validates requests, queues prompt processing, and posts responses in-thread.
- **Inference Worker**: Prompt handling threads call `ReplicateClient.run_inference`, passing the stored LoRA version ID and user prompt. Responses include generated image URLs.
- **Training Workflow**: `src/train_lora.py` zips curated childhood images, uploads them to Replicate, launches Flux LoRA training, and persists the resulting LoRA version to `config/lora_version.json`.
- **Replicate API**: Serves both training (`/trainings`) and inference (`/predictions`). Authentication handled via personal token.
- **Storage**: Transient artifacts (dataset zip, LoRA version JSON) stored locally. Production deployment would prefer secure object storage + secret manager.
- **Observability**: Logs emitted to stdout. Extend with Slack error notifications or monitoring stack as needed.

