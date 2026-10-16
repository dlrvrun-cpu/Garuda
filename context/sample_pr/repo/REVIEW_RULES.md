# Review rules
1. No SOQL or DML inside a loop. Query once, use a Map, update once.
2. Every class declares its sharing (with sharing unless there is a written reason).
3. Triggers stay thin: all logic goes in a handler class.
4. Bind variables only. No string-built SOQL.
5. Every public method has a test that runs with 200 records.
