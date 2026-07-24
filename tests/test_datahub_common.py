from pathlib import Path

from rlmbenchy.datahub.workloads.support.hf import headers, load_rows


def test_load_rows_streams_and_stops_at_max_rows(monkeypatch) -> None:
    yielded: list[int] = []

    class _FakeDataset:
        def __iter__(self):
            for index in range(5):
                yielded.append(index)
                yield {"id": index}

    def _fake_load_dataset(dataset_id, config, *, split, token=None, streaming=False):
        assert dataset_id == "demo/dataset"
        assert config == "default"
        assert split == "test"
        assert streaming is False
        return _FakeDataset()

    monkeypatch.setattr("datasets.load_dataset", _fake_load_dataset)

    rows = load_rows(
        dataset_id="demo/dataset",
        config="default",
        split="test",
        max_rows=2,
    )

    assert rows == [{"id": 0}, {"id": 1}]
    assert yielded == [0, 1]


def test_headers_use_huggingface_token_from_secrets_file(
    monkeypatch, tmp_path: Path
) -> None:
    config_dir = tmp_path / "config"
    monkeypatch.setenv("RLMBENCHY_CONFIG_DIR", str(config_dir))
    monkeypatch.delenv("HF_TOKEN", raising=False)
    secrets_file = config_dir / "secrets.toml"
    secrets_file.parent.mkdir(parents=True, exist_ok=True)
    secrets_file.write_text(
        '[providers.huggingface]\ntoken = "hf-secret"\n',
        encoding="utf-8",
    )

    resolved = headers()

    assert resolved["Authorization"] == "Bearer hf-secret"
