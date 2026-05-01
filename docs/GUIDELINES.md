# Development Guidelines

## Workflow

- **Before any implementation**, always read [`MILESTONES.md`](GITHUB.md) and [`ARCHITECTURE.md`](ARCHITECTURE.md) to understand the current state of the project and the target design
- Implementation follows the issues and milestones defined in [`MILESTONES.md`](MILESTONES.md)
- After completing each task within an issue, tick its checkbox in `MILESTONES.md`
- Implement one task at a time — one task = one commit
- Stop after each task and wait for confirmation before continuing

## Code

- Code must be self-explanatory — avoid comments unless clarifying non-obvious intent
- Follow clean code patterns when possible
- Keep the code simple
## Commits

- One-liner message, small message, no description body
- Use imperative verbs: `Add`, `Fix`, `Update`, `Remove`, `Refactor`, `Create`
- Split logical changes into separate commits

## Testing

- Compile and verify after every change
- Create clean and simple unit tests for each service
