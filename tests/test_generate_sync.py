"""Tests for ``scripts/generate_sync.py``, the async-to-sync code generator."""

from __future__ import annotations

import importlib.util
import inspect
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


def _run(source: str) -> dict[str, object]:
    """Generate the sync code for *source* and execute it."""
    namespace: dict[str, object] = {}
    exec(gen.transform(_source(source)), namespace)  # noqa: S102
    return namespace


def _doc(obj: object) -> str:
    assert obj.__doc__ is not None
    return inspect.cleandoc(obj.__doc__)


class TestStrings:
    def test_runtime_strings_are_copied_verbatim(self) -> None:
        namespace = _run(
            """
            x = "/users/AsyncDiscogsFan/wants"
            msg = "aclose failed"
            """
        )
        assert namespace["x"] == "/users/AsyncDiscogsFan/wants"
        assert namespace["msg"] == "aclose failed"

    def test_all_entries_are_renamed_on_exact_match(self) -> None:
        namespace = _run('__all__ = ["AsyncDiscogs", "AsyncDiscogsFan"]')
        assert namespace["__all__"] == ["Discogs", "AsyncDiscogsFan"]

    def test_lazy_resource_repr_literal_is_renamed(self) -> None:
        namespace = _run(
            """
            class AsyncLazyResource:
                def __repr__(self):
                    n = 1
                    return f"<AsyncLazyResource {n}>"
            """
        )
        cls = namespace["LazyResource"]
        assert isinstance(cls, type)
        assert repr(cls()) == "<LazyResource 1>"

    def test_other_repr_strings_are_copied_verbatim(self) -> None:
        namespace = _run(
            """
            class C:
                def __repr__(self):
                    return "aclose failed /users/AsyncDiscogs/wants"
            """
        )
        cls = namespace["C"]
        assert isinstance(cls, type)
        assert repr(cls()) == "aclose failed /users/AsyncDiscogs/wants"

    def test_docstrings_describe_sync_usage(self) -> None:
        namespace = _run(
            '''
            """An async module for the AsyncDiscogs client."""


            class AsyncDiscogs:
                """Async client for the Discogs API.

                Wraps ``httpx2.AsyncClient``; AsyncDiscogsFan is not renamed.

                Example::

                    async def main():
                        async with AsyncDiscogs(token="...") as client:
                            release = await client.releases.get(352665)
                            async for item in client.search("Nine Inch Nails"):
                                print(item)

                Close it with ``await client.aclose()``.
                """

                async def __aenter__(self):
                    """Create an async Discogs client, an async iterator."""
            '''
        )
        assert namespace["__doc__"] == "A module for the Discogs client."
        cls = namespace["Discogs"]
        assert _doc(cls) == textwrap.dedent(
            """\
            Client for the Discogs API.

            Wraps ``httpx2.Client``; AsyncDiscogsFan is not renamed.

            Example::

                def main():
                    with Discogs(token="...") as client:
                        release = client.releases.get(352665)
                        for item in client.search("Nine Inch Nails"):
                            print(item)

            Close it with ``client.close()``."""
        )
        enter = vars(cls)["__enter__"]
        assert _doc(enter) == "Create a Discogs client, an iterator."

    @pytest.mark.parametrize(
        "prose",
        [
            "Callers must await the result.",
            "The caller has to await.",
            "Use async with to close it.",
        ],
    )
    def test_async_prose_left_in_a_docstring_fails(
        self, prose: str, capsys: pytest.CaptureFixture[str]
    ) -> None:
        source = _source(
            f'''
            async def f():
                """Fetch the release.

                {prose}
                """
            '''
        )
        with pytest.raises(SystemExit) as exc_info:
            gen.transform(source)
        assert exc_info.value.code != 0
        err = capsys.readouterr().err
        assert "<string>:4:" in err
        assert "in f:" in err


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


class TestFieldMixins:
    @pytest.fixture
    def tree(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        src = tmp_path / "_async"
        src.mkdir()
        (src / "proxies.py").write_text(
            "class SoloProxy(AsyncLazyResource[Solo]):\n    pass\n"
        )
        models = tmp_path / "models"
        models.mkdir()
        (models / "things.py").write_text(
            _source(
                """
                class Solo(SDKModel):
                    title: str


                class Parent(SDKModel):
                    name: str


                class Child(Parent):
                    age: int
                """
            )
        )
        monkeypatch.setattr(gen, "ROOT", tmp_path)
        monkeypatch.setattr(gen, "SRC", src)
        monkeypatch.setattr(gen, "MODELS", models)
        return tmp_path

    def test_model_deriving_from_sdk_model_renders(self, tree: Path) -> None:
        rendered = gen._render_field_mixins()
        assert "class SoloFields:" in rendered
        assert "title: str" in rendered

    def test_proxied_model_with_another_base_fails(
        self, tree: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (tree / "_async" / "proxies.py").write_text(
            "class ChildProxy(AsyncLazyResource[Child]):\n    pass\n"
        )
        with pytest.raises(SystemExit) as exc_info:
            gen._render_field_mixins()
        assert exc_info.value.code != 0
        err = capsys.readouterr().err
        assert "Child" in err
        assert "Parent" in err
