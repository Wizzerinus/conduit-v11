from pyconduit.models.bundle import BundleDocument
from pyconduit.models.conduit import Conduit
from pyconduit.models.latex import LatexProblem, LatexRequest
from pyconduit.shared.helpers import get_config

locale = get_config("localization")


def make_conduit(problems: list[LatexProblem], content: dict[str, list[str]]) -> Conduit:
    problems = [prob for prob in problems if prob.conduit_include]
    problem_names = [prob.conduit_num for prob in problems]
    problem_texts = [prob.text for prob in problems]
    return Conduit(content=content, problem_names=problem_names, problem_text_cache=problem_texts)


def no_regen(bundle: BundleDocument, ctx: LatexRequest) -> tuple[bool, str]:
    return False, ""


def regen_once(bundle: BundleDocument, ctx: LatexRequest) -> tuple[bool, str]:
    if bundle.conduit is not None:
        return False, ""

    problems = [prob for prob in bundle.latex.objects if isinstance(prob, LatexProblem)]
    bundle.conduit = make_conduit(problems, {})
    return True, ""


def regen_force(bundle: BundleDocument, ctx: LatexRequest) -> tuple[bool, str]:
    if bundle.conduit is not None and not ctx.force_regen:
        raise ValueError(locale["exceptions"]["need_force_regen"])

    problems = [prob for prob in bundle.latex.objects if isinstance(prob, LatexProblem)]
    bundle.conduit = make_conduit(problems, {})
    return True, ""


def wipe_problem_cache(bundle: BundleDocument, ctx: LatexRequest) -> tuple[bool, str]:
    problems = [prob for prob in bundle.latex.objects if isinstance(prob, LatexProblem) and prob.conduit_include]
    if (len1 := len(bundle.conduit.problem_text_cache)) != (len2 := len(problems)):
        return False, (locale["pages"]["sheet_editor"]["wipe_cache_fail"] % (len1, len2))

    bundle.conduit.problem_text_cache = [prob.text for prob in problems]
    return True, ""


def regen_cache_mid(bundle: BundleDocument, ctx: LatexRequest) -> tuple[bool, str]:
    if bundle.conduit is None:
        problems = [prob for prob in bundle.latex.objects if isinstance(prob, LatexProblem)]
        bundle.conduit = make_conduit(problems, {})
        return True, ""

    old_cache_to_num = {
        text.strip(): num for num, text in zip(bundle.conduit.problem_names, bundle.conduit.problem_text_cache)
    }
    cache_hits = {text.strip(): 0 for text in bundle.conduit.problem_text_cache}

    problems = [prob for prob in bundle.latex.objects if isinstance(prob, LatexProblem) and prob.conduit_include]
    for problem in problems:
        text_strip = problem.text.strip()
        if text_strip in old_cache_to_num:
            cache_hits[text_strip] += 1

    cache_misses = [text for text, hits in cache_hits.items() if hits == 0]
    if cache_misses:
        return False, (
            locale["pages"]["sheet_editor"]["missing_cache_strategy"] % ", ".join(f"'{x}'" for x in cache_misses)
        )

    # the item on index (i) is the new index of the problem, thats text is at index (i) in the cache
    indices_converted = []
    problem_texts = [prob.text.strip() for prob in problems]
    for text in bundle.conduit.problem_text_cache:
        indices_converted.append(problem_texts.index(text.strip()))

    new_contents = {}
    for user, problem_marks in bundle.conduit.content.items():
        new_contents[user] = ["" for _ in range(len(problems))]
        for problem_mark, index in zip(problem_marks, indices_converted):
            new_contents[user][index] = problem_mark

    bundle.conduit = make_conduit(problems, new_contents)
    return True, ""


regen_strategies = {
    "none": no_regen,
    "once": regen_once,
    "force": regen_force,
    "cache-optimal": regen_cache_mid,
    "wipe-cache": wipe_problem_cache,
}
