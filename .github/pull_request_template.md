## What this changes
<!-- One or two sentences. What is different after this merges. -->

## Base
- [ ] Branched from the current tip of `main` (not from another PR's branch)
- [ ] No other open PR touches these files, or the overlap is deliberate and named below
<!--
    git fetch origin && git switch -c <branch> origin/main
    gh pr list --state open --json number,title,headRefName,files
If `main` moved while this was open, merge it in — do not rebase.
Nothing checks this automatically. AGENTS.md explains what it cost last time.
-->

## Scope
- [ ] Every file changed is within the authorized surface for this dev order
- [ ] Anything outside it is called out below and awaits an owner ruling

## Verification
<!-- Which gates were actually run, on which interpreter. Fill from AGENTS.md. -->
- [ ] lint
- [ ] type checks
- [ ] tests with coverage
