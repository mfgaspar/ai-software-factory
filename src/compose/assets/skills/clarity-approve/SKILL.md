---
name: clarity-approve
description: Record a named approver's sign-off on a completed clarity document (or ADR) in its front matter, bound to the document's current content. Refuses drafts and anything changed since it was confirmed. Never approves on anyone's behalf.
argument-hint: "[document path or glob, default every document waiting for approval]"
---

# Approve clarity documents

Documents to approve (empty means every document that is still waiting for approval):

```text
$ARGUMENTS
```

Approvals are a recorded sign-off. They aren't proof of identity: a name is recorded exactly
as the approver gives it. They only exist for documents listed under `approvals` in
`.clarity/config.yml`.

## Steps

1. **Load.**
   - The shipped manifest: `.compose/templates/clarity/manifest.yml`.
   - The `approvals` map from `.clarity/config.yml`: path or glob → names. `decisions/*`
     covers every ADR file.

   If no approvals are configured, say so and stop.
2. **Find the documents.** Use the ones named in the arguments, or every configured one where
   some listed approver has no valid approval. An approval is valid when its `hash` equals the
   document's current body hash.

   **Body hash:** run the manifest's `hash_command` with `FILE` replaced by the quoted path.
   Never compute a hash any other way.
3. **Refuse what can't be approved yet.** Name the reason and the skill that fixes it:
   - **draft**: `status` isn't `complete`, or placeholders remain. Approve only finished work.
   - **edited**: the body hash differs from `reviewed.hash`. The content changed after it was
     confirmed, so it must be re-confirmed first (run `/clarity`).
   - **stale**: a dependency's current hash differs from `reviewed.deps`. Re-confirm first, so
     the approver signs content that reflects the current upstream.
   - ADRs whose `status` is `proposed` or `reconsider`. Settle the decision first.
4. **Ask who is approving.** For each document, show its title, one line on what it says, and
   the approvers still missing. Ask the person in this conversation for their name. Accept it
   only if it is on that document's list (ignore case and surrounding spaces).
5. **Get an explicit approval.** The person must say they approve, for example "I approve
   product/prd.md". "Looks fine" or silence doesn't count. They may approve several documents
   in one sentence if they name them.
6. **Record it.** Append one entry to the document's `approvals` front matter list, with:
   - `by`: the name as listed in the config;
   - `at`: today's date, ISO;
   - `hash`: the current body hash.

   Remove any older entry from the same person. Change nothing else in the file, so the body
   hash stays the same.
7. **Report.** Say what was approved and by whom, and what is still waiting and on whom.

## Rules

- **Never approve on someone else's behalf.** Don't approve for an approver who isn't the
  person in this conversation, and don't fill in a name yourself.
- `auto` mode (or any run with no person present) never records approvals. Report what is
  pending and stop.
- A content edit voids the approvals on that document: their hash no longer matches. That is
  intended. Don't "carry over" an approval to new content.
- When `/clarity` called you, return to it.
