# Framework Profile Fixtures

These small fixtures keep profile behavior easy to inspect.

They are not a public benchmark. They exist so we can check how CodeSight
handles framework hints before we trust those hints in bigger cases.

```bash
codesight verify examples/framework-profiles/fastapi-tenant.sarif \
  --source examples/framework-profiles/fastapi-project \
  --profile fastapi \
  --preview-context

codesight verify examples/framework-profiles/express-path.sarif \
  --source examples/framework-profiles/express-project \
  --profile express \
  --output markdown
```

Available fixtures:

- FastAPI tenant boundary
- Express path traversal
- AI-agent tool validation

Profiles guide the judge. A confirmed finding still needs source, sink, missing
guard, evidence path, fix, and uncertainty.
