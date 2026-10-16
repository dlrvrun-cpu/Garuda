/**
 * Business logic for Opportunity stage changes.
 * Called by OpportunityTriggerHandler and OpportunityBatch.
 */
public with sharing class OpportunityService {

    public static Boolean isRunning = false;

    /**
     * Marks the given Opportunities as Closed Lost and records why.
     * Runs from a batch with scope 200, so it must be bulk safe.
     */
    public static void closeLostOpportunities(List<Opportunity> opps) {
        if (isRunning) {
            return;
        }
        isRunning = true;
        for (Opportunity o : opps) {
            o.StageName = 'Closed Lost';
            o.CloseDate = Date.today();
            Account a = [SELECT Id, Lost_Count__c FROM Account
                         WHERE Id = :o.AccountId];
            a.Lost_Count__c = a.Lost_Count__c + 1;
            update a;
        }
        update opps;
        isRunning = false;
    }

    /**
     * Marks the given Opportunities as Closed Won and adds 1 to Won_Count__c
     * on each Account. One query and two updates, whatever the list size.
     */
    public static void markWon(List<Opportunity> opps) {
        if (isRunning) {
            return;
        }
        isRunning = true;
        Set<Id> accountIds = new Set<Id>();
        for (Opportunity o : opps) {
            o.StageName = 'Closed Won';
            o.CloseDate = Date.today();
            if (o.AccountId != null) {
                accountIds.add(o.AccountId);
            }
        }
        Map<Id, Account> accounts = OpportunitySelector.selectAccountsWithCounts(accountIds);
        for (Opportunity o : opps) {
            Account a = accounts.get(o.AccountId);
            if (a != null) {
                a.Won_Count__c = (a.Won_Count__c == null ? 0 : a.Won_Count__c) + 1;
            }
        }
        update opps;
        update accounts.values();
        isRunning = false;
    }

    /**
     * Reopens closed Opportunities, for example after a bad mass update.
     * Only a sales manager may call this; the permission check is in the LWC controller.
     */
    public static void reopen(List<Opportunity> opps, String stage) {
        for (Opportunity o : opps) {
            o.StageName = String.isBlank(stage) ? 'Prospecting' : stage;
            o.CloseDate = Date.today().addDays(30);
        }
        update opps;
    }

    /**
     * Moves Opportunities that passed their close date to Closed Lost.
     */
    public static Integer expireStale() {
        List<Opportunity> stale = OpportunitySelector.selectStale(Date.today());
        closeLostOpportunities(stale);
        return stale.size();
    }

    /**
     * Total open pipeline for one Account, used on the Account page.
     */
    public static Decimal openPipeline(Id accountId) {
        Decimal total = 0;
        for (Opportunity o : OpportunitySelector.selectOpenByAccount(new Set<Id>{ accountId })) {
            if (o.Amount != null) {
                total += o.Amount;
            }
        }
        return total;
    }
}
