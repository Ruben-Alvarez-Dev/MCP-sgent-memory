// commitlint config — enforces Conventional Commits 1.0 (English, granular),
// per the team norm documented in CONTRIBUTING.md and
// docs/plan/IMPROVEMENT-PLAN.md §3.2 (Open standards matrix: Commits).
//
// Usage (requires Node.js; not vendored as a repo dependency):
//   npx --yes -p @commitlint/cli -p @commitlint/config-conventional \
//     commitlint --edit "$1"          # as a commit-msg hook
//   git log -1 --pretty=%B | npx --yes -p @commitlint/cli \
//     -p @commitlint/config-conventional commitlint

/** @type {import('@commitlint/types').UserConfig} */
module.exports = {
  extends: ['@commitlint/config-conventional'],
  rules: {
    // Types actually in use across this repo's history and CONTRIBUTING.md.
    'type-enum': [
      2,
      'always',
      [
        'feat',
        'fix',
        'docs',
        'refactor',
        'chore',
        'test',
        'ci',
        'perf',
        'build',
        'revert',
      ],
    ],
    'subject-case': [0], // acronyms/proper nouns (Qdrant, Ollama, MCP, ADR-000x) are common
    'header-max-length': [2, 'always', 100],
    'body-leading-blank': [2, 'always'],
    'footer-leading-blank': [1, 'always'],
  },
};
