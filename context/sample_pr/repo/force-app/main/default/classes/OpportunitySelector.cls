/**
 * All Opportunity queries live here.
 */
public with sharing class OpportunitySelector {

    public static List<Opportunity> selectByIds(Set<Id> ids) {
        return [
            SELECT Id, Name, StageName, CloseDate, Amount, AccountId
            FROM Opportunity
            WHERE Id IN :ids
        ];
    }

    public static List<Opportunity> selectOpenByAccount(Set<Id> accountIds) {
        return [
            SELECT Id, Name, StageName, CloseDate, Amount, AccountId
            FROM Opportunity
            WHERE AccountId IN :accountIds AND IsClosed = false
        ];
    }

    public static List<Opportunity> selectStale(Date asOf) {
        return [
            SELECT Id, Name, StageName, CloseDate, Amount, AccountId
            FROM Opportunity
            WHERE CloseDate < :asOf AND IsClosed = false
            LIMIT 10000
        ];
    }

    public static Map<Id, Account> selectAccountsWithCounts(Set<Id> accountIds) {
        return new Map<Id, Account>([
            SELECT Id, Name, Lost_Count__c, Won_Count__c
            FROM Account
            WHERE Id IN :accountIds
        ]);
    }
}
