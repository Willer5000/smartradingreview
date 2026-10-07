# COMMIT 29 — ROLLBACK

Preferred rollback: use GitHub **Revert** on the single Commit 29. That restores the exact repository state immediately before this release and costs one additional deployment only if rollback is actually necessary.

A recovery ZIP is also supplied. It restores the Commit28 package baseline files. Use it only if the GitHub revert workflow is unavailable.
