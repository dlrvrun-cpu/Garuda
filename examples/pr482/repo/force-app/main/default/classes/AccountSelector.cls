public inherited sharing class AccountSelector {
    public static Map<Id, Account> selectTierById(Set<Id> accountIds) {
        return new Map<Id, Account>([
            SELECT Id, Tier__c
            FROM Account
            WHERE Id IN :accountIds
            WITH USER_MODE
        ]);
    }

    public static List<Account> selectByOwner(Id ownerId) {
        return [SELECT Id, Name FROM Account WHERE OwnerId = :ownerId WITH USER_MODE];
    }
}
