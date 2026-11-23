from polisher import latex

SAMPLE = (
    r"We show that $x^2 + y^2 = z^2$ holds \cite{pythagoras} (see Fig.~\ref{fig:a}). "
    r"\begin{equation}E = mc^2\end{equation} This is \textbf{very} good. % TODO fix this"
)


def test_roundtrip_is_lossless():
    protected, mapping = latex.protect(SAMPLE)
    assert latex.restore(protected, mapping) == SAMPLE


def test_math_and_refs_are_hidden_but_prose_is_not():
    protected, _ = latex.protect(SAMPLE)
    for hidden in ("x^2", r"\cite", "pythagoras", "fig:a", "mc^2", "TODO", r"\textbf"):
        assert hidden not in protected
    for visible in ("We show that", "very", "good", "Fig.~"):
        assert visible in protected


def test_text_argument_stays_editable():
    protected, _ = latex.protect(r"\section{Introduction} and \emph{some words}")
    assert "Introduction" in protected and "some words" in protected


def test_missing_token_is_rejected():
    protected, mapping = latex.protect(r"Value $a+b$ here")
    assert latex.restore(protected.replace("@@L0@@", ""), mapping) is None


def test_escaped_symbols_not_treated_as_comment_or_math():
    protected, mapping = latex.protect(r"50\% of the \$5 budget")
    assert latex.restore(protected, mapping) == r"50\% of the \$5 budget"
    assert "50" in protected and "budget" in protected


def test_detection():
    assert latex.looks_like_latex(r"see \cite{a}")
    assert latex.looks_like_latex(r"we have $x_1 = 2$")
    assert latex.looks_like_latex(r"the value $x$ is small")
    assert not latex.looks_like_latex("It costs $5 and I like it")
    assert not latex.looks_like_latex("Just plain prose.")
