@IsTest
private class OpportunityServiceTest {

    @TestSetup
    static void setup() {
        Account acc = new Account(Name = 'Acme', Lost_Count__c = 0);
        insert acc;
        List<Opportunity> opps = new List<Opportunity>();
        for (Integer i = 0; i < 200; i++) {
            opps.add(new Opportunity(
                Name = 'Opp ' + i,
                AccountId = acc.Id,
                StageName = 'Prospecting',
                CloseDate = Date.today().addDays(-1)
            ));
        }
        insert opps;
    }

    @IsTest
    static void closeOne() {
        Opportunity o = [SELECT Id, AccountId FROM Opportunity LIMIT 1];
        Test.startTest();
        OpportunityService.closeLostOpportunities(new List<Opportunity>{ o });
        Test.stopTest();
        Account a = [SELECT Lost_Count__c FROM Account WHERE Id = :o.AccountId];
        System.assertEquals(1, a.Lost_Count__c);
    }

    @IsTest
    static void bulkClose() {
        List<Opportunity> opps = [SELECT Id, AccountId FROM Opportunity];
        Test.startTest();
        OpportunityService.closeLostOpportunities(opps);
        Test.stopTest();
        Account a = [SELECT Lost_Count__c FROM Account LIMIT 1];
        System.assertEquals(200, a.Lost_Count__c);
    }

    @IsTest
    static void expireStaleClosesAll() {
        Test.startTest();
        Integer count = OpportunityService.expireStale();
        Test.stopTest();
        System.assertEquals(200, count);
    }

    @IsTest
    static void markWonBulk() {
        List<Opportunity> opps = [SELECT Id, AccountId FROM Opportunity];
        Test.startTest();
        OpportunityService.markWon(opps);
        Test.stopTest();
        Account a = [SELECT Won_Count__c FROM Account LIMIT 1];
        System.assertEquals(200, a.Won_Count__c);
        System.assertEquals(200, [SELECT COUNT() FROM Opportunity WHERE StageName = 'Closed Won']);
    }

    @IsTest
    static void reopenDefaultsToProspecting() {
        List<Opportunity> opps = [SELECT Id FROM Opportunity LIMIT 5];
        OpportunityService.reopen(opps, null);
        System.assertEquals(5, [SELECT COUNT() FROM Opportunity WHERE StageName = 'Prospecting']);
    }
}
