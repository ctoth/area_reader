# Playable native quest authoring

## Goal
Improve the existing construction kit under Q's authorization to improve area generation and the MOO using the literature. Preserve unrelated work in the original checkout.

## State
Read the existing compiler, authoring tests, source writer, reset compilation, and live MOO quest validation/evaluators/loader. Work is isolated from untracked world/Evennia experiments. No publication requested.
New regressions first reproduced the compiler failures. Compiler fixes are implemented and the changed test_authoring.py passes. Unrelated uv lock churn from environment settings was removed. The MOO validator counterpart is delegated to in-MOO codex862 at Q's explicit direction.

## Decisions and why
Fix existing owner contracts: stage opening honors needs, rejects duplicate dependencies, checks state arguments against actual live evaluator arity, and refuses a local giver with no mob placement. Retain native quest JSON, existing SourceError paths, and existing authoring tests. IVIE's missing-placement failures motivate rejecting demonstrably unbindable givers before loading; no claim of complete puzzle solvability.

## Surprises
The live engine accepts threshold-based predecessor graphs, including cycles made openable by an alternative predecessor. Compiler stage_order instead requires every predecessor. The loader requires a live giver instance; resolving the prototype does not establish one.

## Next step
Inspect the final source delta, add any missing boundary controls, and commit the substantive change with this note. Publication remains governed by Q's explicit posting instruction.
