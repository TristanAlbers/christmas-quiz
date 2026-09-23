# Polling UI stability guideline

The quiz uses 500 ms HTMX polling for live state. Polling must not recreate controls that a user can still be interacting with when their semantic context has not changed. This applies to functional/admin UI as well as polished player UI: redrawing a select, input, form, or button at polling cadence can reset selection or focus, interrupt hover state, and make clicks unreliable.

Use these rules for polled views:

- Keep text-entry controls outside the normal polling swap target and replace them only when their run/question/permission context actually changes.
- For a stable non-text interactive subtree that must remain inside a polled fragment, give its root a stable `id` and preserve it with `hx-preserve`, or split it into a separate non-polled target.
- Never require a user to complete an interaction between two 500 ms polls.
- Add a browser regression test for interactive controls inside polled views; the test should keep the interaction active across at least one poll before submitting or continuing.
- It is fine to replace controls when their semantic context genuinely changes, such as a new run, question, global state, or permission set.

This complements the live-view rules in `docs/architecture.md`. In particular, `hx-preserve` is not a substitute for the existing structural handling of text-input focus.
