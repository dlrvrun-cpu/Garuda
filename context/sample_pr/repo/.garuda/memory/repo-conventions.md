# Repo conventions (Garuda memory)
- Queries live in *Selector classes. Services call selectors, never inline SOQL.
- Handlers use a static Boolean guard (isRunning) to stop trigger recursion.
- Account rollup fields (Lost_Count__c, Won_Count__c) are updated in one bulk update at the end.
- Batch jobs run with scope 200, so every service method must be bulk safe.
