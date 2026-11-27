# Evidence for hypothesis_testing.py

Sample outside state for the lost count PR, in the same spirit as `context/sample_pr/ci-test-run.log`.
In a live setup each file comes from a real probe:

| File | Live probe |
|---|---|
| `../../context/sample_pr/ci-test-run.log` | the PR's CI run (`sf apex run test`) |
| `base-run.log` | the same test class, run on `main` |
| `bulkClose-debug.log` | the Apex debug log for `OpportunityServiceTest.bulkClose` |
