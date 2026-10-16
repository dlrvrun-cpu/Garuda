# Repo conventions

- Trigger framework: every trigger delegates to a *TriggerHandler that extends TriggerHandler.
- Selectors live in /classes/*Selector.cls; services call selectors, never query directly.
- Finance owns discount rules; discount changes need a finance sign-off note in the PR.
