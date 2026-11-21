# Acting on review feedback

Reviewers lack context and are sometimes wrong, so feedback is checked before it is built.

1. **Read all of it first.** If any item is unclear, change nothing and ask about the unclear items: items are often related, and half-understood feedback becomes wrong code.
2. **Check each item against this codebase.** Is it correct here? Would it break existing behaviour? Is the current code that way for a reason (compatibility, an earlier decision)? If it contradicts something the owner already decided, ask the owner before acting.
3. **Check it is needed.** A request to "implement X properly" gets a search for real usage first. Unused code gets a proposal to delete it instead.
4. **Answer with substance.** State the fix and where it is, or push back with the technical reason and the evidence (code, test, search result). No thanks, no "you're absolutely right". If your pushback was wrong, say what you checked and fix it.
5. **Fix one item at a time**, in this order: breakage and security, then small fixes, then larger changes. Test after each, then run the whole flow in `SKILL.md` again on the result.

On GitHub, reply in the review thread (`gh api repos/{owner}/{repo}/pulls/{pr}/comments/{id}/replies`), not as a new top-level comment.
