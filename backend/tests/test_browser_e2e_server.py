import pytest

from scripts.serve_browser_e2e import existing_database_path, persistent_database_path


def test_persistent_e2e_database_is_optional_and_scoped_to_evaluation(tmp_path):
    repository_root = tmp_path / "veda"
    evaluation_dir = repository_root / "evaluation"
    evaluation_dir.mkdir(parents=True)

    assert persistent_database_path(None, repository_root=repository_root) is None
    database_path = persistent_database_path(
        str(evaluation_dir / "fulltext-smoke.sqlite3"), repository_root=repository_root
    )

    assert database_path == evaluation_dir / "fulltext-smoke.sqlite3"
    assert not database_path.exists()


@pytest.mark.parametrize(
    "relative_path",
    [
        "outside.sqlite3",
        "evaluation/../outside.sqlite3",
        "evaluation/not-a-database.json",
    ],
)
def test_persistent_e2e_database_rejects_paths_outside_evaluation_or_wrong_suffix(
    tmp_path, relative_path
):
    repository_root = tmp_path / "veda"
    (repository_root / "evaluation").mkdir(parents=True)

    with pytest.raises(ValueError):
        persistent_database_path(
            str(repository_root / relative_path), repository_root=repository_root
        )


def test_persistent_e2e_database_never_overwrites_an_existing_file(tmp_path):
    repository_root = tmp_path / "veda"
    evaluation_dir = repository_root / "evaluation"
    evaluation_dir.mkdir(parents=True)
    database_path = evaluation_dir / "existing.sqlite3"
    database_path.write_bytes(b"preserve-me")

    with pytest.raises(FileExistsError):
        persistent_database_path(str(database_path), repository_root=repository_root)

    assert database_path.read_bytes() == b"preserve-me"


def test_existing_e2e_database_must_exist_and_be_scoped_to_evaluation(tmp_path):
    repository_root = tmp_path / "veda"
    evaluation_dir = repository_root / "evaluation"
    evaluation_dir.mkdir(parents=True)
    database_path = evaluation_dir / "preserved.sqlite3"

    with pytest.raises(FileNotFoundError):
        existing_database_path(str(database_path), repository_root=repository_root)

    database_path.write_bytes(b"preserve-me")
    assert (
        existing_database_path(str(database_path), repository_root=repository_root) == database_path
    )
    assert database_path.read_bytes() == b"preserve-me"


@pytest.mark.parametrize("relative_path", ["outside.sqlite3", "evaluation/not-a-database.json"])
def test_existing_e2e_database_rejects_out_of_scope_or_wrong_suffix(tmp_path, relative_path):
    repository_root = tmp_path / "veda"
    evaluation_dir = repository_root / "evaluation"
    evaluation_dir.mkdir(parents=True)
    requested = repository_root / relative_path
    requested.parent.mkdir(parents=True, exist_ok=True)
    requested.write_bytes(b"preserve-me")

    with pytest.raises(ValueError):
        existing_database_path(str(requested), repository_root=repository_root)
