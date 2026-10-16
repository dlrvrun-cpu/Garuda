@IsTest
private class OpportunityTriggerTest {
    @IsTest
    static void bulkUpdate() {
        List<Account> accts = new List<Account>();
        for (Integer i = 0; i < 200; i++) {
            accts.add(new Account(Name = 'Acct ' + i, Tier__c = 'Gold'));
        }
        insert accts;
        List<Opportunity> opps = new List<Opportunity>();
        for (Account a : accts) {
            opps.add(new Opportunity(Name = 'Opp', AccountId = a.Id,
                StageName = 'Prospecting', CloseDate = Date.today(), Amount = 1000));
        }
        insert opps;
        for (Opportunity o : opps) {
            o.Amount = 2000;
        }
        Test.startTest();
        update opps;
        Test.stopTest();
        System.assertEquals(200, [SELECT COUNT() FROM Opportunity WHERE Amount = 2000]);
    }
}
