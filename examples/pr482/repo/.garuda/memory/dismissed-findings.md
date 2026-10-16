# Dismissed findings (team said: not a bug)

- OpportunityTriggerHandler.countByStage: dynamic SOQL flagged as injection. Dismissed: the
  query string is a constant and `stage` is a bind variable, so it is safe.
- InvoiceService.totalsByAccount: aggregate query flagged as non-selective. Dismissed: IsWon
  plus AccountId IN is selective in this org.
