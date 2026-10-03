# Polling UI stability guideline

The quiz uses 500 ms HTMX polling for live state. Polling must not recreate or temporarily relocate controls that a user can still be interacting with when their semantic context has not changed. This applies to functional/admin UI as well as polished player UI: redrawing a select, input, form, or button at polling cadence can reset selection or focus, interrupt a native control, break hover/press state, and make clicks unreliable.

Use these rules for polled views:

- Keep rapidly changing read-only status inside the normal polling swap target.
- Keep package-wide filesystem verification out of normal polling: once a pinned snapshot has passed cold process verification, warm projections must not reread or hash unrelated media files.
- Keep user-operated controls outside that target while their interaction context is unchanged.
- Replace an interactive pane out-of-band only when its authoritative context genuinely changes, such as a new run, question, global state, team activity state, hint/reverse eligibility, permission set, or available READY package options.
- Do not use `hx-preserve` as the primary protection for actively used controls. Preservation can retain a DOM node while HTMX temporarily relocates it during a parent swap, which can still interrupt native controls or pointer interaction.
- Never require a user to complete an interaction between two 500 ms polls.
- Keep the stable synchronization container unchanged; polls continue to use `drop` and commands `replace`.
- Disable command buttons while their request is in flight and retain server-side idempotency.
- Add browser regression coverage for interaction races. Where practical, test real pointer-down/poll/pointer-up behavior or stable node identity/focus rather than only programmatic `.click()` or value assignment.

Text-entry controls such as the answer field should remain mounted so typing, focus and caret survive normal polling. The same principle applies to Game Master inputs and native controls such as package selectors.

This complements the live-view rules in `docs/architecture.md`; it does not change the 500 ms polling architecture or authorize a different frontend transport.
