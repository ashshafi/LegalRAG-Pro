"""Explicit-root immutable sidecar store for candidate crop-lineage bindings."""

from __future__ import annotations

from pathlib import Path
import re

from .crop_lineage import (
    CandidateCropLineageBinding,
    CandidateCropLineageError,
    dumps_candidate_crop_lineage_binding,
    loads_candidate_crop_lineage_binding,
    validate_candidate_crop_lineage_binding,
)


_SHA256_ID_RE = re.compile(r"^sha256:([0-9a-f]{64})$")


class CandidateCropLineageStoreError(RuntimeError):
    """Raised when immutable crop-lineage storage cannot be proven."""


class CandidateCropLineageStore:
    """Store crop-lineage bindings beneath one caller-supplied explicit root."""

    def __init__(self, root: str | Path) -> None:
        if isinstance(root, str) and not root.strip():
            raise CandidateCropLineageStoreError("root must not be empty.")

        self.root = Path(root)
        if str(self.root) in {"", "."}:
            raise CandidateCropLineageStoreError(
                "root must be an explicit non-current-directory path."
            )

    @staticmethod
    def _sha_id_hex(value: str, *, field_name: str) -> str:
        if not isinstance(value, str):
            raise CandidateCropLineageStoreError(
                f"{field_name} must be a sha256:<hex> identifier."
            )

        match = _SHA256_ID_RE.fullmatch(value)
        if match is None:
            raise CandidateCropLineageStoreError(
                f"{field_name} must be a sha256:<hex> identifier."
            )

        return match.group(1)

    def _candidate_folder(self, candidate_record_id: str) -> Path:
        candidate_hex = self._sha_id_hex(
            candidate_record_id,
            field_name="candidate_record_id",
        )
        return self.root / "candidate_crop_lineage" / candidate_hex

    def _binding_path(
        self,
        *,
        candidate_record_id: str,
        binding_id: str,
    ) -> Path:
        binding_hex = self._sha_id_hex(
            binding_id,
            field_name="binding_id",
        )
        return self._candidate_folder(candidate_record_id) / f"{binding_hex}.json"

    def publish_binding(
        self,
        binding: CandidateCropLineageBinding,
    ) -> None:
        """Publish one immutable binding, allowing an exact idempotent repeat."""

        try:
            validate_candidate_crop_lineage_binding(binding)
            text = dumps_candidate_crop_lineage_binding(binding)
        except CandidateCropLineageError as exc:
            raise CandidateCropLineageStoreError(
                "Binding failed validation before publication."
            ) from exc

        payload = text.encode("utf-8")
        path = self._binding_path(
            candidate_record_id=binding.candidate_record_id,
            binding_id=binding.binding_id,
        )
        path.parent.mkdir(parents=True, exist_ok=True)

        if path.exists():
            existing = path.read_bytes()
            if existing == payload:
                return
            raise CandidateCropLineageStoreError(
                "Immutable binding path already exists with different bytes."
            )

        created = False
        try:
            with path.open("xb") as handle:
                created = True
                handle.write(payload)
                handle.flush()

            if path.read_bytes() != payload:
                raise CandidateCropLineageStoreError(
                    "Published binding bytes failed exact read-back verification."
                )
        except Exception:
            if created and path.exists():
                try:
                    path.unlink()
                except OSError:
                    pass
            raise

    def load_binding(
        self,
        *,
        candidate_record_id: str,
        binding_id: str,
    ) -> CandidateCropLineageBinding:
        path = self._binding_path(
            candidate_record_id=candidate_record_id,
            binding_id=binding_id,
        )

        if not path.is_file():
            raise CandidateCropLineageStoreError("Binding does not exist.")

        try:
            binding = loads_candidate_crop_lineage_binding(
                path.read_text(encoding="utf-8")
            )
        except (UnicodeDecodeError, CandidateCropLineageError) as exc:
            raise CandidateCropLineageStoreError(
                "Stored binding is invalid."
            ) from exc

        if binding.candidate_record_id != candidate_record_id:
            raise CandidateCropLineageStoreError(
                "Stored binding candidate coordinate differs."
            )
        if binding.binding_id != binding_id:
            raise CandidateCropLineageStoreError(
                "Stored binding identity differs."
            )

        return binding

    def list_candidate_bindings(
        self,
        candidate_record_id: str,
    ) -> tuple[CandidateCropLineageBinding, ...]:
        folder = self._candidate_folder(candidate_record_id)
        if not folder.exists():
            return ()
        if not folder.is_dir():
            raise CandidateCropLineageStoreError(
                "Candidate crop-lineage coordinate is not a directory."
            )

        bindings = []
        for path in sorted(folder.glob("*.json")):
            binding_hex = path.stem
            binding = self.load_binding(
                candidate_record_id=candidate_record_id,
                binding_id=f"sha256:{binding_hex}",
            )
            bindings.append(binding)

        return tuple(bindings)


__all__ = [
    "CandidateCropLineageStore",
    "CandidateCropLineageStoreError",
]
