public with sharing class InvoiceService {
    public static Map<Id, Decimal> totalsByAccount(Set<Id> accountIds) {
        Map<Id, Decimal> totals = new Map<Id, Decimal>();
        for (AggregateResult ar : [
            SELECT AccountId acct, SUM(Amount) total
            FROM Opportunity
            WHERE AccountId IN :accountIds AND IsWon = true
            WITH USER_MODE
            GROUP BY AccountId
        ]) {
            totals.put((Id) ar.get('acct'), (Decimal) ar.get('total'));
        }
        return totals;
    }
}
