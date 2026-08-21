from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

import pytest

from finance_data.immutable_dataset import (
    dumps_immutable_dataset_document,
    loads_immutable_dataset_document,
    validate_immutable_dataset_document,
)
from finance_data.immutable_dataset_publication import (
    FinanceImmutableDatasetPublicationError,
    publish_immutable_finance_dataset,
)
from finance_data.immutable_provider import ImmutableDatasetProvider
from test_finance_data_immutable_provider import _document


def _validated():
    document = _document()
    return validate_immutable_dataset_document(
        document,
        expected_provider_id=document["provider_id"],
        expected_dataset_id=document["dataset_id"],
        expected_dataset_version=document["dataset_version"],
    )


def _canonical_bytes(path: Path) -> bytes:
    payload = path.read_text(encoding="utf-8")
    data = loads_immutable_dataset_document(payload)
    return dumps_immutable_dataset_document(data).encode("utf-8")


def _staging_files(target: Path) -> list[Path]:
    return list(target.parent.glob(f".{target.name}-*.tmp"))


def test_publishes_exact_canonical_dataset_and_provider_accepts_it(tmp_path):
    dataset = _validated()
    target = tmp_path / "immutable-dataset.json"

    result = publish_immutable_finance_dataset(dataset, target_path=target)

    assert result == target
    assert result.read_bytes() == _canonical_bytes(result)
    assert _staging_files(target) == []

    provider = ImmutableDatasetProvider(
        dataset_path=result,
        expected_provider_id=dataset.provider_id,
        expected_dataset_id=dataset.dataset_id,
        expected_dataset_version=dataset.dataset_version,
    )
    assert provider.dataset_identity == dataset.dataset_identity
    assert provider.workspace == dataset.workspace
    assert provider.list_companies() == dataset.companies
    assert provider.list_securities() == dataset.securities


def test_identical_republication_is_idempotent(tmp_path):
    dataset = _validated()
    target = tmp_path / "immutable-dataset.json"

    first = publish_immutable_finance_dataset(dataset, target_path=target)
    before = first.read_bytes()
    second = publish_immutable_finance_dataset(dataset, target_path=target)

    assert second == first
    assert second.read_bytes() == before
    assert _staging_files(target) == []


def test_conflicting_existing_target_fails_closed_without_overwrite(tmp_path):
    dataset = _validated()
    target = tmp_path / "immutable-dataset.json"
    target.write_bytes(b"conflicting-existing-state")
    before = target.read_bytes()

    with pytest.raises(FinanceImmutableDatasetPublicationError, match="conflicts"):
        publish_immutable_finance_dataset(dataset, target_path=target)

    assert target.read_bytes() == before
    assert _staging_files(target) == []


def test_nonregular_target_fails_closed(tmp_path):
    dataset = _validated()
    target = tmp_path / "immutable-dataset.json"
    target.mkdir()

    with pytest.raises(
        FinanceImmutableDatasetPublicationError,
        match="plain regular",
    ):
        publish_immutable_finance_dataset(dataset, target_path=target)


def test_target_symlink_fails_closed(tmp_path):
    dataset = _validated()
    target_file = tmp_path / "target.json"
    target_file.write_bytes(b"state")
    target = tmp_path / "immutable-dataset.json"
    try:
        target.symlink_to(target_file)
    except OSError as exc:
        pytest.skip(f"symlink unavailable on this platform: {exc}")

    with pytest.raises(
        FinanceImmutableDatasetPublicationError,
        match="plain regular",
    ):
        publish_immutable_finance_dataset(dataset, target_path=target)


def test_parent_symlink_escape_fails_closed(tmp_path):
    dataset = _validated()
    outside = tmp_path / "outside"
    outside.mkdir()
    linked = tmp_path / "linked"
    try:
        linked.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlink unavailable on this platform: {exc}")
    target = linked / "immutable-dataset.json"

    with pytest.raises(
        FinanceImmutableDatasetPublicationError,
        match="plain directory",
    ):
        publish_immutable_finance_dataset(dataset, target_path=target)

    assert not (outside / "immutable-dataset.json").exists()


def test_invalid_dataset_identity_fails_before_publication(tmp_path):
    dataset = _validated()
    bad = replace(dataset, dataset_identity="sha256:" + "f" * 64)
    target = tmp_path / "immutable-dataset.json"

    with pytest.raises(
        FinanceImmutableDatasetPublicationError,
        match="reconstructed",
    ):
        publish_immutable_finance_dataset(bad, target_path=target)

    assert not target.exists()
    assert _staging_files(target) == []


def test_non_path_and_relative_target_fail_before_publication(tmp_path, monkeypatch):
    dataset = _validated()

    with pytest.raises(
        FinanceImmutableDatasetPublicationError,
        match="pathlib.Path",
    ):
        publish_immutable_finance_dataset(dataset, target_path=str(tmp_path / "x.json"))  # type: ignore[arg-type]

    monkeypatch.chdir(tmp_path)
    with pytest.raises(
        FinanceImmutableDatasetPublicationError,
        match="absolute",
    ):
        publish_immutable_finance_dataset(dataset, target_path=Path("x.json"))


def test_hardlink_unavailable_fails_closed_and_cleans_staging(tmp_path, monkeypatch):
    dataset = _validated()
    target = tmp_path / "immutable-dataset.json"

    def unavailable(*args, **kwargs):
        raise OSError("hard links unavailable")

    monkeypatch.setattr(os, "link", unavailable)

    with pytest.raises(
        FinanceImmutableDatasetPublicationError,
        match="create-if-absent",
    ):
        publish_immutable_finance_dataset(dataset, target_path=target)

    assert not target.exists()
    assert _staging_files(target) == []


def test_concurrent_identical_publication_is_idempotent(tmp_path, monkeypatch):
    dataset = _validated()
    target = tmp_path / "immutable-dataset.json"
    real_link = os.link

    def concurrent_identical(staging, destination):
        real_link(staging, destination)
        raise FileExistsError("simulated concurrent winner")

    monkeypatch.setattr(os, "link", concurrent_identical)

    result = publish_immutable_finance_dataset(dataset, target_path=target)

    assert result == target
    assert target.read_bytes() == _canonical_bytes(target)
    assert _staging_files(target) == []


def test_concurrent_conflicting_publication_fails_closed(tmp_path, monkeypatch):
    dataset = _validated()
    target = tmp_path / "immutable-dataset.json"

    def concurrent_conflict(staging, destination):
        Path(destination).write_bytes(b"concurrent-conflict")
        raise FileExistsError("simulated concurrent conflict")

    monkeypatch.setattr(os, "link", concurrent_conflict)

    with pytest.raises(
        FinanceImmutableDatasetPublicationError,
        match="Concurrent.*conflicts",
    ):
        publish_immutable_finance_dataset(dataset, target_path=target)

    assert target.read_bytes() == b"concurrent-conflict"
    assert _staging_files(target) == []
