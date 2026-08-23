"""Step 13A ownership, ordered fingerprint, and cache tests."""

from database import db
from models import (
    Document,
    DocumentComparison,
    Project,
    User,
)
from services.document_comparison_service import (
    DocumentComparisonNotFoundError,
    DocumentComparisonValidationError,
    create_ordered_comparison_fingerprint,
    list_owned_comparisons,
    prepare_owned_document_comparison,
    require_owned_comparison,
    require_owned_document_pair,
)


def _owned_pair(user):
    project = Project(
        user_id=user,
        title="Owned comparison project",
    )
    document_a = Document(
        project=project,
        filename="requirements-v1.pdf",
        file_path="requirements-v1.pdf",
        extracted_text="Minimum password length is eight.",
    )
    document_b = Document(
        project=project,
        filename="requirements-v2.pdf",
        file_path="requirements-v2.pdf",
        extracted_text="Minimum password length is twelve.",
    )
    db.session.add_all(
        [
            project,
            document_a,
            document_b,
        ]
    )
    db.session.commit()

    return (
        document_a,
        document_b,
    )


def _second_user_document():
    outsider = User(
        name="Other User",
        email="other@example.com",
    )
    outsider.set_password(
        "StrongPass123!"
    )

    project = Project(
        owner=outsider,
        title="Private project",
    )
    document = Document(
        project=project,
        filename="private.pdf",
        file_path="private.pdf",
        extracted_text="Private information.",
    )

    db.session.add_all(
        [
            outsider,
            project,
            document,
        ]
    )
    db.session.commit()

    return document


def test_owned_pair_preserves_a_to_b_order(app, user):
    with app.app_context():
        document_a, document_b = _owned_pair(user)

        result_a, result_b = require_owned_document_pair(
            owner_id=user,
            document_a_id=document_a.id,
            document_b_id=document_b.id,
        )

        assert result_a.id == document_a.id
        assert result_b.id == document_b.id


def test_same_document_pair_is_rejected(app, user):
    with app.app_context():
        document_a, _ = _owned_pair(user)

        try:
            require_owned_document_pair(
                owner_id=user,
                document_a_id=document_a.id,
                document_b_id=document_a.id,
            )
        except DocumentComparisonValidationError as error:
            assert "different documents" in str(error)
        else:
            raise AssertionError(
                "Comparing a document with itself must fail."
            )


def test_foreign_document_is_hidden_by_ownership_boundary(app, user):
    with app.app_context():
        document_a, _ = _owned_pair(user)
        foreign_document = _second_user_document()

        try:
            require_owned_document_pair(
                owner_id=user,
                document_a_id=document_a.id,
                document_b_id=foreign_document.id,
            )
        except DocumentComparisonNotFoundError:
            pass
        else:
            raise AssertionError(
                "Another user's document must not be comparable."
            )


def test_invalid_document_ids_are_rejected_before_query(app, user):
    with app.app_context():
        _, document_b = _owned_pair(user)

        try:
            require_owned_document_pair(
                owner_id=user,
                document_a_id="not-an-id",
                document_b_id=document_b.id,
            )
        except DocumentComparisonValidationError as error:
            assert "Document A" in str(error)
        else:
            raise AssertionError(
                "Invalid document IDs must fail validation."
            )


def test_ordered_fingerprint_is_stable_and_directional(app, user):
    with app.app_context():
        document_a, document_b = _owned_pair(user)

        first = create_ordered_comparison_fingerprint(
            document_a=document_a,
            document_b=document_b,
        )
        repeated = create_ordered_comparison_fingerprint(
            document_a=document_a,
            document_b=document_b,
        )
        reversed_pair = create_ordered_comparison_fingerprint(
            document_a=document_b,
            document_b=document_a,
        )

        assert first == repeated
        assert len(first) == 64
        assert first != reversed_pair


def test_fingerprint_invalidates_when_either_source_changes(app, user):
    with app.app_context():
        document_a, document_b = _owned_pair(user)

        before = create_ordered_comparison_fingerprint(
            document_a=document_a,
            document_b=document_b,
        )

        document_b.extracted_text = (
            "Minimum password length is sixteen."
        )
        db.session.commit()

        after = create_ordered_comparison_fingerprint(
            document_a=document_a,
            document_b=document_b,
        )

        assert before != after


def test_prepare_reuses_only_exact_completed_ordered_comparison(app, user):
    with app.app_context():
        document_a, document_b = _owned_pair(user)

        fingerprint = create_ordered_comparison_fingerprint(
            document_a=document_a,
            document_b=document_b,
        )

        comparison = DocumentComparison(
            user_id=user,
            document_a_id=document_a.id,
            document_b_id=document_b.id,
            summary="Cached comparison",
            provider="test",
            model="test-model",
            status="Completed",
            source_fingerprint=fingerprint,
        )
        db.session.add(comparison)
        db.session.commit()

        prepared = prepare_owned_document_comparison(
            owner_id=user,
            document_a_id=document_a.id,
            document_b_id=document_b.id,
        )

        assert prepared.reusable_comparison is not None
        assert prepared.reusable_comparison.id == comparison.id

        reversed_prepared = prepare_owned_document_comparison(
            owner_id=user,
            document_a_id=document_b.id,
            document_b_id=document_a.id,
        )

        assert reversed_prepared.reusable_comparison is None


def test_force_bypasses_existing_comparison_cache(app, user):
    with app.app_context():
        document_a, document_b = _owned_pair(user)

        fingerprint = create_ordered_comparison_fingerprint(
            document_a=document_a,
            document_b=document_b,
        )

        db.session.add(
            DocumentComparison(
                user_id=user,
                document_a_id=document_a.id,
                document_b_id=document_b.id,
                provider="test",
                model="test-model",
                status="Completed",
                source_fingerprint=fingerprint,
            )
        )
        db.session.commit()

        prepared = prepare_owned_document_comparison(
            owner_id=user,
            document_a_id=document_a.id,
            document_b_id=document_b.id,
            force=True,
        )

        assert prepared.reusable_comparison is None


def test_failed_or_stale_comparison_is_not_reused(app, user):
    with app.app_context():
        document_a, document_b = _owned_pair(user)

        fingerprint = create_ordered_comparison_fingerprint(
            document_a=document_a,
            document_b=document_b,
        )

        db.session.add_all(
            [
                DocumentComparison(
                    user_id=user,
                    document_a_id=document_a.id,
                    document_b_id=document_b.id,
                    provider="test",
                    model="test-model",
                    status="Failed",
                    source_fingerprint=fingerprint,
                ),
                DocumentComparison(
                    user_id=user,
                    document_a_id=document_a.id,
                    document_b_id=document_b.id,
                    provider="test",
                    model="test-model",
                    status="Completed",
                    source_fingerprint="0" * 64,
                ),
            ]
        )
        db.session.commit()

        prepared = prepare_owned_document_comparison(
            owner_id=user,
            document_a_id=document_a.id,
            document_b_id=document_b.id,
        )

        assert prepared.reusable_comparison is None


def test_saved_comparison_access_and_history_are_owner_scoped(app, user):
    with app.app_context():
        document_a, document_b = _owned_pair(user)
        foreign_document = _second_user_document()
        foreign_project = foreign_document.project

        foreign_second = Document(
            project=foreign_project,
            filename="private-2.pdf",
            file_path="private-2.pdf",
            extracted_text="Private second version.",
        )
        db.session.add(foreign_second)
        db.session.flush()

        owned = DocumentComparison(
            user_id=user,
            document_a_id=document_a.id,
            document_b_id=document_b.id,
            provider="test",
            model="test-model",
            status="Completed",
            source_fingerprint="a" * 64,
        )
        foreign = DocumentComparison(
            user_id=foreign_project.user_id,
            document_a_id=foreign_document.id,
            document_b_id=foreign_second.id,
            provider="test",
            model="test-model",
            status="Completed",
            source_fingerprint="b" * 64,
        )
        db.session.add_all(
            [
                owned,
                foreign,
            ]
        )
        db.session.commit()

        assert require_owned_comparison(
            comparison_id=owned.id,
            owner_id=user,
        ).id == owned.id

        history = list_owned_comparisons(
            owner_id=user
        )

        assert [
            comparison.id
            for comparison in history
        ] == [owned.id]

        try:
            require_owned_comparison(
                comparison_id=foreign.id,
                owner_id=user,
            )
        except DocumentComparisonNotFoundError:
            pass
        else:
            raise AssertionError(
                "Foreign comparison history must stay hidden."
            )
