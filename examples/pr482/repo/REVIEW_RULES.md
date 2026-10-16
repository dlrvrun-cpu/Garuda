# Review rules (Acme Sales org)

1. Bulkify everything: no SOQL or DML inside loops; triggers must handle 200 records.
2. Every class declares sharing. `without sharing` only in classes named *SystemService.
3. SOQL lives in selector classes (/classes/*Selector.cls) and uses WITH USER_MODE.
4. New fields need FLS in the Sales_User permission set, not only the Admin profile.
5. Tests: 200-record bulk test, real asserts, no SeeAllData=true.
6. No hardcoded record Ids, profile names, or org URLs.
