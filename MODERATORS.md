# Moderators

Moderators review new tracks and fixes: they check the markup against satellite imagery or a recorded lap, look for
duplicates and the source, and approve the PR. The rules are in [CONTRIBUTING.md](CONTRIBUTING.md#how-it-is-checked),
the deadlines in [Review times](CONTRIBUTING.md#review-times).

## A new track, step by step

1. **Review the issue** within 3 days: assign yourself, check the source, duplicates and the confirmations.
2. **Add `accepted`** (or ask for changes with `needs-changes`). The bot validates the JSON and either opens the PR
   `track/issue-<N>` or comments the errors and moves the issue to `needs-changes`.
3. **Review the bot's PR**: the `validate` check is green, the warnings in the description are looked at, the lines and
   the outline match satellite imagery or a recorded lap.
4. **Approve and merge** within 14 days of the submission. The merge closes the issue.

Details: [Submissions from the app](CONTRIBUTING.md#submissions-from-the-app).

| GitHub | Region / tracks | Since |
|---|---|---|
| [@tooszovski](https://github.com/tooszovski) | maintainer, all tracks, schema and tooling | 2026-10 |

## Becoming a moderator

Open an issue with the [Become a moderator](../../issues/new?template=moderator.yml) form. What we look for:

- you drive the tracks you want to review (track days, a club, a series) and know their layouts;
- you are comfortable with GitHub: PRs, review comments, approving;
- you can answer a submission within 3 days and decide within 14 days;
- a few submitted or fixed tracks of your own help, but are not required.

A new moderator starts with the tracks of their region; the schema and tooling stay with the maintainer.

## Adding a moderator (maintainer)

1. Give the person **Write** access to the repository (Settings → Collaborators).
2. Add their handle to `.github/CODEOWNERS` on the `/tracks/` line (only on the paths of their region if that is
   agreed, e.g. `/tracks/ru/`).
3. Add a row to the table above.
4. Close the application issue with a link to the PR.

The issue bot needs the repository setting Settings → Actions → General → Workflow permissions → **Allow GitHub
Actions to create and approve pull requests** (it opens the PR with `GITHUB_TOKEN`; no other secret is needed).

Stepping down or a long absence: remove the handle from CODEOWNERS and the table, take away Write access.
