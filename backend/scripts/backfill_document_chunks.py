"""Create or refresh searchable chunks for existing documents."""

from __future__ import annotations

from app import create_app
from models import Document
from services.document_chunk_service import (
    DocumentChunkError,
    ensure_owned_document_chunks,
)


def main() -> int:
    app = create_app()

    with app.app_context():
        documents = (
            Document.query
            .filter(
                Document.user_id.isnot(None),
                Document.extracted_text.isnot(None),
            )
            .order_by(
                Document.id.asc()
            )
            .all()
        )

        readable_documents = [
            document
            for document in documents
            if str(
                document.extracted_text or ""
            ).strip()
        ]

        rebuilt_count = 0
        reused_count = 0
        failed_count = 0

        print(
            "Readable documents found:",
            len(readable_documents),
        )

        for document in readable_documents:
            owner_id = document.user_id

            if owner_id is None:
                failed_count += 1

                print(
                    f"[SKIPPED] Document {document.id}: "
                    "no direct document owner."
                )

                continue

            try:
                result = ensure_owned_document_chunks(
                    document_id=document.id,
                    user_id=owner_id,
                )

            except DocumentChunkError as error:
                failed_count += 1

                print(
                    f"[FAILED] Document {document.id} "
                    f"({document.filename}): {error}"
                )

                continue

            if result.rebuilt:
                rebuilt_count += 1
                status = "BUILT"
            else:
                reused_count += 1
                status = "CURRENT"

            print(
                f"[{status}] Document {document.id} "
                f"({document.filename}): "
                f"{len(result.chunks)} chunks"
            )

        print()
        print("Document chunk backfill complete.")
        print("Built or rebuilt:", rebuilt_count)
        print("Already current:", reused_count)
        print("Failed or skipped:", failed_count)

        return 1 if failed_count else 0


if __name__ == "__main__":
    raise SystemExit(main())