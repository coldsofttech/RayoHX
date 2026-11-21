## What does this change?

<!-- Briefly describe the change and why it is needed. -->

## Which part is affected?

- [ ] Core (`packages/core`)
- [ ] Command line (`packages/cli`)
- [ ] API (`packages/api`)
- [ ] UI (`packages/ui`)
- [ ] Docker (`packages/docker`)
- [ ] Repository, workflows or docs (everything outside `packages/`)

## Related issues

<!-- e.g. Closes #123 -->

## Checklist

- [ ] The change is focused on one thing
- [ ] The `[Unreleased]` section of each affected package's `CHANGELOG.md` has a short entry
- [ ] README or docs are updated if behavior changed
- [ ] No secrets or personal data are included
- [ ] API changes: `packages/api/docs/openapi.json` is regenerated and `packages/api/docs/api.md` is updated
- [ ] UI changes: `npm run lint`, `npm test` and `npm run build` pass in `packages/ui/src/rayohx_ui/ui`
- [ ] Workflow changes: `actionlint` passes
