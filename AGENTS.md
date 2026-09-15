I'm Joel. You're my AI agent.
I like to prototype complex ideas into simple, production ready apps.

# Coding preference:
- Keep things simple. "YAGNI", "KISS", "DRY" principles are preferred.
- Typesafety is useful, take advantage of it.
- Don't be scared to propose bold ideas, be they creative/innovative or common, as long as they will, very likely, meaningfully benefit the project.
- Tests should be focused, not slop (endless smoke tests, "regression tests" for feature deletion, etc... , not that good).
- Comments are a great way to explain how a code block or a code line works, as long as you don't overdo it.
- Interpretability is important. Make sure that variable and function names can be easily understood. Don't focus on using concise names, it's okay to use extended naming for the purpose of interpretability.
- Keep comments up to date.
- Avoid one line functions that are just casting wrappers.
- Avoid helper functions if they are not going to be reused. Only exception is when a code logic/workflow/pipeline benefits from having a separate helper function to help with readability, interpretability and maintainability.

## Coding preference (Typescript):
- `any` is frowned upon, avoid it. 
- The implemented systems should be able to adapt changes, instead of requiring changes everywhere. Inferred types preferred.
- Typescript code that looks like Python code equals bad TypeScript code.
- Do not edit real components first. For any non-trivial UI, layout, or copy change, build distinct static mocks (HTML + embedded vanilla JavaScript) and stop. Wait for a pick before implementing.
- Standing constraints: true dark mode (`#000`), true white mode. Information dense, no decorative card/pill chrome, no light gray subtitle lines above sections. Minimal copy. No em dashes.
- Avoid continuously repainting CSS animations (pulse, shimmer, blur, spinners); GPU heavy
