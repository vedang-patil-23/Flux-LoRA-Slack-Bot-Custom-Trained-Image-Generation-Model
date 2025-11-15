"""Lightweight Replicate REST helper for Flux LoRA training + inference."""

from __future__ import annotations

import io
import json
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential


REPLICATE_API = "https://api.replicate.com/v1"


class ReplicateError(RuntimeError):
    """Raised for Replicate API failures."""


class ReplicateClient:
    def __init__(self, api_token: str, timeout: float = 30.0) -> None:
        headers = {
            "Authorization": f"Token {api_token}",
            "User-Agent": "InspireWorks-SlackBot/1.0",
        }
        self._client = httpx.Client(base_url=REPLICATE_API, headers=headers, timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def _check(self, response: httpx.Response) -> Dict[str, Any]:
        if response.status_code >= 400:
            raise ReplicateError(f"{response.status_code} {response.text}")
        return response.json()

    def upload_dataset(self, archive_path: Path) -> str:
        """Upload a zipped dataset; returns replicate dataset URL."""
        if not archive_path.exists():
            raise FileNotFoundError(archive_path)

        with archive_path.open("rb") as file_handle:
            files = {"file": (archive_path.name, file_handle, "application/zip")}
            response = self._client.post("/files", files=files, headers={"Authorization": self._client.headers["Authorization"]})
        data = self._check(response)
        return data["upload_url"]

    def start_training(
        self,
        *,
        model_owner: str,
        model_name: str,
        input_params: Dict[str, Any],
    ) -> Dict[str, Any]:
        payload = {"model": f"{model_owner}/{model_name}", "input": input_params}
        response = self._client.post("/trainings", json=payload)
        return self._check(response)

    def get_training(self, training_id: str) -> Dict[str, Any]:
        response = self._client.get(f"/trainings/{training_id}")
        return self._check(response)

    def poll_training(self, training_id: str, interval_seconds: int = 30) -> Dict[str, Any]:
        """Poll until training finishes."""
        while True:
            training = self.get_training(training_id)
            status = training.get("status")
            if status in {"succeeded", "failed", "canceled"}:
                return training
            time.sleep(interval_seconds)

    def get_prediction(self, prediction_id: str) -> Dict[str, Any]:
        response = self._client.get(f"/predictions/{prediction_id}")
        return self._check(response)

    def poll_prediction(self, prediction_id: str, interval_seconds: float = 2.0) -> Dict[str, Any]:
        while True:
            prediction = self.get_prediction(prediction_id)
            status = prediction.get("status")
            if status in {"succeeded", "failed", "canceled"}:
                return prediction
            time.sleep(interval_seconds)

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.RequestError),
    )
    def run_inference(
        self,
        *,
        version: str,
        prompt: str,
        negative_prompt: Optional[str] = None,
        num_outputs: int = 1,
        guidance: float = 3.5,
        seed: Optional[int] = None,
        aspect_ratio: str = "1:1",
    ) -> Dict[str, Any]:
        payload = {
            "version": version,
            "input": {
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "num_outputs": num_outputs,
                "guidance": guidance,
                "seed": seed,
                "aspect_ratio": aspect_ratio,
            },
        }
        # Remove null values for cleaner payload.
        payload["input"] = {k: v for k, v in payload["input"].items() if v is not None}
        response = self._client.post("/predictions", json=payload)
        data = self._check(response)
        status = data.get("status")
        if status not in {"succeeded", "failed", "canceled"}:
            prediction_id = data["id"]
            data = self.poll_prediction(prediction_id)
        return data


def zip_dataset(source_dir: Path, archive_path: Path) -> Path:
    """Compress a dataset folder into a .zip archive."""
    import zipfile

    if not source_dir.is_dir():
        raise NotADirectoryError(source_dir)

    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in source_dir.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(source_dir))
    return archive_path


