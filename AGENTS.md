# android-skills

Agent skills for Android development. Each skill is `<category>/<skill-name>/SKILL.md`, optionally with sibling reference files or `scripts/`. `README.md` lists every skill and its sources.

## Rules for skill content

- **Google's documentation is the source of truth** (developer.android.com, the Compose API guidelines, official samples). When a skill disagrees with it, change the skill. A skill may only go further than Google where the rule is stricter; mark those rules `(stricter than Google)`.
- Every `SKILL.md` starts with a `Sources of truth:` line linking the Google pages it follows. Re-check those pages when changing the skill.
- Verify API names, artifacts and versions against current docs before writing them. Point to release pages instead of hardcoding versions.
- Never use the em dash character; use a plain dash.
- Keep comments in code samples and scripts to what is strictly necessary.
- Write explanations in your own words. Code may be adapted only from Apache 2.0 or MIT first-party sources; add any new source to `THIRD_PARTY_NOTICES.md`. Never copy from other agent-skill repositories. The Gradle User Manual is CC BY-NC-SA: use it for facts only.

## Structure and naming

| Category | Holds |
|---|---|
| `architecture/` | App layers: architecture, domain, data, ViewModels |
| `ui/` | Compose UI, navigation, images, accessibility, performance |
| `async/` | Coroutines, Flow, networking |
| `testing/` | Test strategy, Compose tests, emulator tooling |
| `build/` | Gradle build logic and build performance |
| `migrations/` | Migrations from older APIs |

- Names are kebab-case and start with `android-` (platform and architecture), `compose-` (Compose UI), `gradle-` (build) or `migrate-` (migrations). The folder name and frontmatter `name` must match.
- A new category must also be added to `skills` in `.claude-plugin/plugin.json`, the table above, and `README.md`.
- Refer to other skills by name in backticks (`compose-lists`); the validator checks that they exist.

## Writing skills

- Descriptions stay under 400 characters: what the skill covers, then `Use when ...` with trigger words. Every description is loaded into every agent session.
- Write `description` as a double-quoted YAML string. Descriptions contain `: `, which is invalid in an unquoted YAML value and makes strict parsers skip the skill.
- Keep `SKILL.md` under 500 lines. Move material only some tasks need (large mapping tables, migration guides) into a sibling file and link it from `SKILL.md`.
- Prefer extending an existing skill over adding one that overlaps it.

## After changing skills

1. `python3 tools/validate_skills.py` must pass. CI runs it on every push and pull request.
2. After adding, renaming or removing a skill, run `./install.sh` to refresh the symlinks, update `README.md`, and update references to the old name.
