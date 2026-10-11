"""Tests for ``scripts/generate_sync.py``, the async-to-sync code generator."""

from __future__ import annotations

import importlib.util
import sys
import textwrap
from pathlib import Path
from types import ModuleType

import pytest

# The installed-wheel CI job installs only the `test` group, which lacks the
# generator's own dependency.
pytest.importorskip("ast_comments")

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "generate_sync.py"


def _load_generator() -> ModuleType:
    # `scripts/` is not a package, so load the file directly.
    spec = importlib.util.spec_from_file_location("generate_sync", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gen = _load_generator()


def _source(text: str) -> str:
    return textwrap.dedent(text).lstrip("\n")


def _expected(text: str) -> str:
    return gen.HEADER + "\n" + _source(text)


class TestDirectiveValidation:
    def test_directive_without_else_as_only_statement_fails(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        source = _source(
            """
            async def f():
                if True:  # ASYNC
                    await asyncio.sleep(1)
            """
        )
        with pytest.raises(SystemExit) as exc_info:
            gen.transform(source)
        assert exc_info.value.code != 0
        err = capsys.readouterr().err
        assert "<string>:2:" in err
        assert "in f:" in err

    def test_directive_emptying_a_nested_block_fails(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        source = _source(
            """
            async def f(ready):
                if ready:
                    if True:  # ASYNC
                        await asyncio.sleep(1)
                return 1
            """
        )
        with pytest.raises(SystemExit):
            gen.transform(source)
        err = capsys.readouterr().err
        assert "<string>:3:" in err
        assert "in f:" in err

    def test_detached_directive_comment_fails(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        source = _source(
            """
            async def f():
                # ASYNC
                if True:
                    await asyncio.sleep(1)
                else:
                    time.sleep(1)
            """
        )
        with pytest.raises(SystemExit) as exc_info:
            gen.transform(source)
        assert exc_info.value.code != 0
        err = capsys.readouterr().err
        assert "<string>:3:" in err
        assert "in f:" in err

    def test_directive_comment_on_the_next_line_fails(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        source = _source(
            """
            class C:
                async def g(self):
                    if True:
                        # ASYNC
                        await asyncio.sleep(1)
                    else:
                        time.sleep(1)
            """
        )
        with pytest.raises(SystemExit):
            gen.transform(source)
        err = capsys.readouterr().err
        assert "<string>:3:" in err
        assert "in C.g:" in err

    def test_directive_with_else_splices_the_else_body(self) -> None:
        source = _source(
            """
            async def f():
                if True:  # ASYNC
                    await asyncio.sleep(1)
                else:
                    time.sleep(1)
            """
        )
        assert gen.transform(source) == _expected(
            """
            def f():
                time.sleep(1)
            """
        )

    def test_directive_without_else_next_to_another_statement_is_removed(
        self,
    ) -> None:
        source = _source(
            """
            class C:
                if True:  # ASYNC
                    x = 1
                y = 2
            """
        )
        assert gen.transform(source) == _expected(
            """
            class C:
                y = 2
            """
        )

    def test_directive_as_only_statement_of_an_else_drops_the_else(self) -> None:
        source = _source(
            """
            async def f(ready):
                if ready:
                    start()
                else:
                    if True:  # ASYNC
                        await asyncio.sleep(1)
                return 1
            """
        )
        assert gen.transform(source) == _expected(
            """
            def f(ready):
                if ready:
                    start()
                return 1
            """
        )


class TestRunOnMalformedSource:
    @pytest.fixture
    def tree(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        src = tmp_path / "src" / "_async"
        src.mkdir(parents=True)
        (src / "ok.py").write_text("async def g():\n    return 1\n")
        (src / "bad.py").write_text(
            "async def f():\n    if True:  # ASYNC\n        await x\n"
        )
        dst = tmp_path / "src" / "_sync"
        dst.mkdir()
        (dst / "existing.py").write_text("sentinel\n")
        fields = tmp_path / "_lazy_fields.py"
        fields.write_text("fields sentinel\n")
        monkeypatch.setattr(gen, "ROOT", tmp_path)
        monkeypatch.setattr(gen, "SRC", src)
        monkeypatch.setattr(gen, "DST", dst)
        monkeypatch.setattr(gen, "FIELDS_MODULE", fields)
        return tmp_path

    def test_failing_run_leaves_generated_files_untouched(
        self,
        tree: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setattr(sys, "argv", ["generate_sync.py"])
        with pytest.raises(SystemExit) as exc_info:
            gen.main()
        assert exc_info.value.code != 0
        assert "src/_async/bad.py:2: in f:" in capsys.readouterr().err
        dst = tree / "src" / "_sync"
        assert sorted(p.name for p in dst.iterdir()) == ["existing.py"]
        assert (dst / "existing.py").read_text() == "sentinel\n"
        assert (tree / "_lazy_fields.py").read_text() == "fields sentinel\n"

    def test_check_fails(
        self,
        tree: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setattr(sys, "argv", ["generate_sync.py", "--check"])
        with pytest.raises(SystemExit) as exc_info:
            gen.main()
        assert exc_info.value.code != 0
        assert "src/_async/bad.py:2: in f:" in capsys.readouterr().err
