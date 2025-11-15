from pathlib import Path
import zipfile

import pytest

from src.replicate_client import zip_dataset


def test_zip_dataset(tmp_path: Path):
    source_dir = tmp_path / "dataset"
    source_dir.mkdir()
    (source_dir / "image1.jpg").write_bytes(b"123")
    (source_dir / "nested").mkdir()
    (source_dir / "nested" / "image2.jpg").write_bytes(b"456")

    archive_path = tmp_path / "dataset.zip"
    result = zip_dataset(source_dir, archive_path)

    assert result.exists()
    with zipfile.ZipFile(result, "r") as archive:
        names = set(archive.namelist())
    assert names == {"image1.jpg", "nested/image2.jpg"}


def test_zip_dataset_invalid_dir(tmp_path: Path):
    with pytest.raises(NotADirectoryError):
        zip_dataset(tmp_path / "missing", tmp_path / "out.zip")


