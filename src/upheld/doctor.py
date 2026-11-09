"""What `upheld doctor` checks: what's installed, what `auto` will pick on this machine and why, and which models are
already downloaded. It loads no model, so it takes a second or two (most of it importing torch)."""

import importlib.util
import platform
from dataclasses import dataclass
from importlib import metadata

from upheld.evidence import SentenceEmbedder
from upheld.verify import (
    GraniteJudgeVerifier,
    LettuceVerifier,
    MiniCheckVerifier,
    _memory_gib,
    explain_default_verifier,
)

# extra -> (distribution, module) pairs it installs
EXTRAS: dict[str, list[tuple[str, str]]] = {
    "minicheck": [("torch", "torch"), ("transformers", "transformers")],
    "lettuce": [("lettucedetect", "lettucedetect")],
    "dense": [("sentence-transformers", "sentence_transformers")],
    "judge": [("llama-cpp-python", "llama_cpp"), ("transformers", "transformers")],
    "api": [("fastapi", "fastapi"), ("uvicorn", "uvicorn")],
    "mcp": [("mcp", "mcp")],
}

# (repo, file that marks it as downloaded, approximate download)
MODELS: dict[str, tuple[str, str, str]] = {
    "minicheck": (MiniCheckVerifier.DEFAULT_MODEL, "config.json", "about 3 GB"),
    "lettuce": (LettuceVerifier.DEFAULT_MODEL, "config.json", "about 0.6 GB"),
    "judge": (GraniteJudgeVerifier.GGUF_REPO, GraniteJudgeVerifier.GGUF_FILE, "8.7 GB"),
    "judge-tokenizer": (GraniteJudgeVerifier.TOKENIZER, "tokenizer_config.json", "a few MB"),
    "dense": (SentenceEmbedder.DEFAULT_MODEL, "config.json", "about 0.1 GB"),
}

# The models each verifier loads.
VERIFIER_MODELS = {
    "ensemble": ["minicheck", "lettuce"],
    "ensemble+judge": ["minicheck", "lettuce", "judge", "judge-tokenizer"],
    "judge": ["judge", "judge-tokenizer"],
    "minicheck": ["minicheck"],
    "lettuce": ["lettuce"],
    "lexical": [],
}


@dataclass
class Extra:
    name: str
    installed: bool
    versions: list[str]


@dataclass
class Model:
    repo: str
    downloaded: bool | None  # None: huggingface_hub isn't installed, so there's no cache to look in
    size: str


@dataclass
class Diagnosis:
    upheld: str
    python: str
    system: str
    memory_gib: float
    extras: list[Extra]
    device: str | None
    verifier: str
    reason: str
    runnable: bool  # whether `auto` would load: its verifier's extras are installed
    retrieval: str
    models: list[Model]


def _version(dist: str) -> str | None:
    try:
        return metadata.version(dist)
    except metadata.PackageNotFoundError:
        return None


def _device() -> str | None:
    if importlib.util.find_spec("torch") is None:
        return None
    import torch

    return "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"


def _downloaded(repo: str, filename: str) -> bool | None:
    if importlib.util.find_spec("huggingface_hub") is None:
        return None
    from huggingface_hub import try_to_load_from_cache

    return isinstance(try_to_load_from_cache(repo, filename), str)


def diagnose() -> Diagnosis:
    extras = []
    for name, packages in EXTRAS.items():
        versions = [(dist, _version(dist)) for dist, module in packages if importlib.util.find_spec(module) is not None]
        extras.append(Extra(name, len(versions) == len(packages), [f"{d} {v}" for d, v in versions if v]))
    installed = {e.name for e in extras if e.installed}

    verifier, reason = explain_default_verifier()
    needs = {"ensemble": {"minicheck", "lettuce"}, "judge": {"judge"}}[verifier]
    retrieval = "hybrid" if "dense" in installed else "bm25"
    wanted = VERIFIER_MODELS[verifier] + (["dense"] if retrieval == "hybrid" else [])
    models = [Model(MODELS[m][0], _downloaded(MODELS[m][0], MODELS[m][1]), MODELS[m][2]) for m in wanted]
    return Diagnosis(
        upheld=_version("upheld") or "unknown",
        python=platform.python_version(),
        system=f"{platform.system()} {platform.machine()}",
        memory_gib=_memory_gib(),
        extras=extras,
        device=_device(),
        verifier=verifier,
        reason=reason,
        runnable=needs <= installed,
        retrieval=retrieval,
        models=models,
    )
