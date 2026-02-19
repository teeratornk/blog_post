"""Shared test fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_DRAFTS = FIXTURES_DIR / "sample_drafts"
SAMPLE_BIB = FIXTURES_DIR / "sample_bib"
SAMPLE_LOGS = FIXTURES_DIR / "sample_logs"
SAMPLE_CONFIG = FIXTURES_DIR / "sample_config.yaml"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def sample_drafts_dir() -> Path:
    return SAMPLE_DRAFTS


@pytest.fixture
def sample_bib_dir() -> Path:
    return SAMPLE_BIB


@pytest.fixture
def sample_intro_md() -> str:
    return (SAMPLE_DRAFTS / "01_introduction.md").read_text(encoding="utf-8")


@pytest.fixture
def sample_methodology_md() -> str:
    return (SAMPLE_DRAFTS / "02_methodology.md").read_text(encoding="utf-8")


@pytest.fixture
def sample_bib() -> str:
    return (SAMPLE_BIB / "references.bib").read_text(encoding="utf-8")


@pytest.fixture
def sample_config_path() -> Path:
    return SAMPLE_CONFIG


@pytest.fixture
def success_log_path() -> Path:
    return SAMPLE_LOGS / "success.log"


@pytest.fixture
def error_log_path() -> Path:
    return SAMPLE_LOGS / "error.log"


@pytest.fixture
def tmp_output_dir(tmp_path: Path) -> Path:
    out = tmp_path / "output"
    out.mkdir()
    return out


@pytest.fixture
def sample_latex() -> str:
    """A minimal valid LaTeX document for testing."""
    return r"""\documentclass[12pt]{article}
\usepackage{amsmath}
\usepackage{graphicx}
\usepackage{natbib}

\title{Test Article}
\date{\today}

\begin{document}
\maketitle

\section{Introduction}
%% SAFE_ZONE_START
This is the introduction paragraph with a citation \cite{hughes2000finite}.
%% SAFE_ZONE_END

\section{Methods}
%% SAFE_ZONE_START
We present the following equation:
%% SAFE_ZONE_END

\begin{equation}
\label{eq:pde}
\mathcal{L}[u](\mathbf{x}) = f(\mathbf{x})
\end{equation}

%% SAFE_ZONE_START
As shown in Equation \ref{eq:pde}, the operator acts on the solution field.
%% SAFE_ZONE_END

\begin{figure}[htbp]
\centering
\includegraphics[width=0.8\textwidth]{convergence.png}
\caption{Training convergence}
\label{fig:convergence}
\end{figure}

\bibliographystyle{elsarticle-num}
\bibliography{references}

\end{document}
"""
