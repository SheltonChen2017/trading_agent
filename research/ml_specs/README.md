# ML research specs

`volatility-discovery-v1.json` is a review-ready discovery specification, not
an approved experiment and not evidence that a model works. Its companion
review request deliberately has `review_status=review_required`.

Before a real run, an identified reviewer must inspect the dataset semantics,
historical universe, ordered features, baselines, target, horizon, split and
embargo, research-look dimensions, statistical gates, failure slices, and
mandate ceiling. Create a separate `SpecReviewAttestation` JSON with the exact
spec hash, `decision=approved`, and
`review_scope=research_behavior_and_gates`. Never replace the review request
with an approval merely to make automation pass.

The spec expects a separately materialized point-in-time dataset with the
matching feature-set, label, universe, benchmark, and baseline columns. The
dataset must first pass `materialize-dataset`, which stores it beneath its
content hash. A positive discovery may only generate a distinct confirmation
spec/request against a different untouched dataset hash; that generated spec
requires its own review attestation.
