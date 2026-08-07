# Proceedings of the Wizengamot

*Full court. All fifty members. For a code review.*

---

"The charges against the accused are as follows: that it did knowingly
and in full awareness of the illegality of its actions, having received
a previous written warning from the Ministry of Static Analysis, commit
directly to `main` on the second of August, thus placing the entire
repository in grave peril."

"Interrogative," said Dumbledore. "Did the accused have tests?"

"...I beg your pardon?"

"Tests, Cornelius. It is a simple enough question. Did the change ship
with a regression test that would fail without it?"

"That is hardly —"

"It is **entirely** relevant, and I would remind the court that a green
suite is not proof of correctness; it is proof only of what was
asserted. Furthermore, no member of this body has yet applied the
reverse mutation. Break the fix. Confirm the test goes red. Restore it
in a `finally` block. Until then the court is reviewing its own
assumptions and calling them evidence."

## Standing Orders

1. Every commit in the range gets an explicit disposition. Never review
   only the tip. The tip is the smile on the crocodile.
2. Maintain the P0–P3 ledger. Resolved items are **retained**, not
   deleted. Erasing a resolved finding erases the reason it existed.
3. Verify before fixing. Classify as confirmed, partially correct, or
   false alarm. Then search for the generalized instance — there is
   almost always a generalized instance.
4. "It passed on my machine" is not a defence and never has been.

*The accused was cleared of all charges and required to write
`tests/test_module_hygiene.py`.*
