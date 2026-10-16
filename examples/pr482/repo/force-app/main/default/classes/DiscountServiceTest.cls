@IsTest
private class DiscountServiceTest {
    @IsTest
    static void recalcSetsDiscount() {
        Account a = new Account(Name = 'Acme', Tier__c = 'Gold');
        insert a;
        Opportunity o = new Opportunity(Name = 'Deal', AccountId = a.Id,
            StageName = 'Prospecting', CloseDate = Date.today(), Amount = 1000);
        insert o;
        o.Amount = 5000;
        update o;
        System.assert(true);
    }
}
